"""
GIS Ingestion Template — Flow C

Factory that creates Airflow DAGs for raw GIS file ingestion.
Pipeline scope: source check → download → validate → upload to MinIO.

Intentionally stops before PostGIS loading. Bronze table DDL and
ogr2ogr import are handled in a separate pipeline once the data has
been explored and the schema is confirmed.

Reusable across: CAOP, OSM, PDM, ARU, and any future GIS source.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class GISIngestionConfig:
    """
    All parameters needed to instantiate a GIS ingestion DAG.

    --- URL resolution ---
    download_url accepts three formats:
        "https://..."           → used as-is
        "var:<KEY>"             → read from Airflow Variable at runtime
        "param:<KEY>"           → read from dag_run.conf at runtime
                                  (used for sources with dynamic URLs, e.g. CAOP)

    --- Version resolution ---
    source_version accepts:
        "2024"                  → used as-is
        None                    → read from dag_run.conf[version_param_key] at runtime
                                  (used for annually-released datasets like CAOP)

    --- Layer name resolution ---
    expected_layers and layer_name_fn are mutually exclusive:
        expected_layers=[...]   → static list, used as-is
        layer_name_fn=callable  → called with the resolved version string
                                  (used when layer names embed the version, e.g. CAOP)
    """

    # --- DAG identity ---
    dag_id: str
    source_name: str        # Short identifier used in paths/logs — e.g. "caop", "pdm_lisbon"
    description: str

    # --- Source ---
    download_url: str       # URL, "var:<KEY>", or "param:<KEY>"
    expected_format: str    # File extension: "gpkg", "zip", "shp", "geojson", "pbf"

    # --- GIS validation expectations ---
    expected_layers: list[str]          # Static layer names; [] if using layer_name_fn
    expected_crs_epsg: Optional[int]    # Assert CRS; None = log warning only
    min_feature_count: int              # Minimum features per layer (sanity floor)
    max_feature_count: int              # Maximum features per layer (sanity ceiling)
    min_file_size_bytes: int            # Raise if download is smaller than this

    # --- MinIO storage ---
    minio_bucket: str       # e.g. "raw"
    minio_prefix: str       # e.g. "caop" → stored at raw/caop/{version}/{filename}

    # --- Scheduling ---
    schedule: Optional[str]     # Cron, "@yearly", "@monthly", or None (manual trigger)
    # start_date is optional. When None:
    #   - For manual-trigger DAGs (schedule=None): defaults to yesterday UTC — the DAG is
    #     immediately triggerable without implying anything about historical runs.
    #   - For scheduled DAGs: you MUST set this explicitly to control backfill behaviour.
    start_date: Optional[datetime] = None

    # --- Version (static or dynamic) ---
    # Set to a string for sources with fixed versions (e.g. Census 2021 → "2021").
    # Set to None for annually-released datasets: version is then required as a
    # trigger param, read from dag_run.conf[version_param_key] at runtime.
    source_version: Optional[str] = None
    version_param_key: str = "version"  # dag_run.conf key when source_version is None

    # --- Dynamic layer names ---
    # When layer names embed the version (e.g. "Cont_AAF_CAOP2024"), set this
    # callable instead of expected_layers. It receives the resolved version string
    # and returns the list of expected layer names.
    # Set expected_layers=[] when using layer_name_fn.
    layer_name_fn: Optional[Callable[[str], list[str]]] = None

    # --- DAG-level Airflow Params ---
    # Shown in the "Trigger DAG" dialog. Define params that operators must supply
    # at trigger time (e.g. version and download_url for CAOP).
    # Format: {"param_key": {"default": ..., "description": ...}}
    dag_params: dict = field(default_factory=dict)

    # --- DAG settings ---
    tags: list[str] = field(default_factory=list)
    retries: int = 2
    retry_delay_minutes: int = 5
    email_on_failure: bool = False


# ---------------------------------------------------------------------------
# Runtime resolution helpers
# ---------------------------------------------------------------------------


def _resolve_url(url_or_ref: str, context: dict) -> str:
    """
    Returns the actual download URL from one of three sources:
        "https://..."    → literal URL, returned as-is
        "var:<KEY>"      → Airflow Variable
        "param:<KEY>"    → dag_run.conf key (supplied at trigger time)
    """
    if url_or_ref.startswith("var:"):
        from airflow.models import Variable

        key = url_or_ref[4:]
        url = Variable.get(key)
        log.info(f"Resolved URL from Airflow Variable '{key}': {url}")
        return url

    if url_or_ref.startswith("param:"):
        key = url_or_ref[6:]
        url = context["dag_run"].conf.get(key, "")
        if not url:
            raise ValueError(
                f"DAG trigger param '{key}' is required but was not provided. "
                f"Supply it via 'Trigger DAG w/ config' in the Airflow UI."
            )
        log.info(f"Resolved URL from trigger param '{key}': {url}")
        return url

    return url_or_ref


def _resolve_version(config: GISIngestionConfig, context: dict) -> str:
    """
    Returns the version string from config, dag_run.conf, or Airflow Params.

    Resolution order:
      1. config.source_version  (static, e.g. "2021")
      2. dag_run.conf[key]      (manual trigger with config)
      3. context["params"][key]  (Param default — used by scheduled runs)
    """
    if config.source_version is not None:
        return config.source_version

    # Manual trigger: version comes from dag_run.conf
    version = context["dag_run"].conf.get(config.version_param_key, "")
    if version:
        log.info(f"Resolved version from dag_run.conf '{config.version_param_key}': {version}")
        return version

    # Scheduled run: Airflow Params provide the default
    version = context.get("params", {}).get(config.version_param_key, "")
    if version:
        log.info(f"Resolved version from Param default '{config.version_param_key}': {version}")
        return version

    raise ValueError(
        f"DAG trigger param '{config.version_param_key}' is required but was not provided. "
        f"Supply it via 'Trigger DAG w/ config' in the Airflow UI."
    )


def _resolve_layers(config: GISIngestionConfig, version: str) -> list[str]:
    """
    Returns the expected layer names from the config.
    If layer_name_fn is set, calls it with the resolved version.
    """
    if config.layer_name_fn is not None:
        layers = config.layer_name_fn(version)
        log.info(f"Resolved expected layers from layer_name_fn (version={version}): {layers}")
        return layers
    return config.expected_layers


# ---------------------------------------------------------------------------
# DAG factory
# ---------------------------------------------------------------------------


def create_gis_ingestion_dag(config: GISIngestionConfig):
    """
    Returns an Airflow DAG configured for the given GISIngestionConfig.

    Task graph:
        check_source_availability
               ↓
          download_file
               ↓
         validate_gis_file
               ↓
         upload_to_minio
            ↙       ↘
      cleanup_temp  log_run_metadata
    """
    import pendulum
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    resolved_start_date = config.start_date or pendulum.yesterday("UTC")

    if config.schedule is not None and config.start_date is None:
        raise ValueError(
            f"[{config.dag_id}] start_date must be set explicitly for scheduled DAGs "
            f"(schedule='{config.schedule}'). It controls backfill behaviour."
        )

    default_args = {
        "owner": "data-engineering",
        "retries": config.retries,
        "retry_delay": timedelta(minutes=config.retry_delay_minutes),
        "email_on_failure": config.email_on_failure,
    }

    airflow_params = {
        key: Param(
            default=spec.get("default", ""),
            description=spec.get("description", ""),
            type="string",
        )
        for key, spec in config.dag_params.items()
    }

    @dag(
        dag_id=config.dag_id,
        description=config.description,
        schedule=config.schedule,
        start_date=resolved_start_date,
        catchup=False,
        default_args=default_args,
        params=airflow_params,
        tags=["ingestion", "gis", "minio"] + config.tags,
    )
    def gis_ingestion_dag():

        # ------------------------------------------------------------------
        # Task 1: Check source availability
        # ------------------------------------------------------------------

        @task()
        def check_source_availability(**context) -> dict:
            """
            Verifies the download URL is reachable before attempting a large download.

            Tries HEAD first (fast, no body transferred). Falls back to a streaming
            GET that is immediately closed if the server does not support HEAD
            (e.g. mapas.ine.pt closes the connection on HEAD requests).

            Returns basic HTTP metadata for downstream tasks.
            Fails the DAG early if the source is unreachable or returns an error.
            """
            import requests

            url = _resolve_url(config.download_url, context)
            version = _resolve_version(config, context)

            log.info(f"[{config.source_name}] Checking source (version={version}): {url}")

            try:
                resp = requests.head(url, timeout=30, allow_redirects=True)
                resp.raise_for_status()
                log.info(f"[{config.source_name}] HEAD succeeded.")
            except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as head_exc:
                log.warning(
                    f"[{config.source_name}] HEAD failed ({head_exc}), "
                    f"falling back to streaming GET."
                )
                with requests.get(url, stream=True, timeout=30, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    # Close immediately — we only need the status and headers.

            info = {
                "url": url,
                "version": version,
                "http_status": resp.status_code,
                "content_length_bytes": int(resp.headers.get("content-length", 0)),
                "content_type": resp.headers.get("content-type", "unknown"),
                "last_modified": resp.headers.get("last-modified", "unknown"),
            }
            log.info(f"[{config.source_name}] Source available: {info}")
            return info

        # ------------------------------------------------------------------
        # Task 2: Download file
        # ------------------------------------------------------------------

        @task()
        def download_file(source_info: dict) -> dict:
            """
            Streams the file to a local temp directory, computing its SHA-256
            hash on the fly (no second pass needed).

            If the downloaded file is a ZIP archive, it is automatically
            extracted and the inner file matching expected_format is returned.
            This handles sources like CAOP where DGT wraps the .gpkg in a .zip.

            Returns the local path to the GIS file (never the zip), temp dir,
            file size, and hash of the original download.
            """
            import zipfile
            import requests

            url = source_info["url"]
            version = source_info["version"]
            temp_dir = Path(tempfile.mkdtemp(prefix=f"gis_{config.source_name}_"))

            # Derive download filename from the URL's last path segment
            url_filename = url.split("/")[-1].split("?")[0] or f"{config.source_name}_{version}"
            dest_path = temp_dir / url_filename

            log.info(f"[{config.source_name}] Downloading → {dest_path}")

            sha256 = hashlib.sha256()

            with requests.get(url, stream=True, timeout=600) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):  # 4 MB chunks
                        f.write(chunk)
                        sha256.update(chunk)

            file_size = dest_path.stat().st_size
            log.info(f"[{config.source_name}] Download complete — {file_size:,} bytes")

            if file_size < config.min_file_size_bytes:
                raise ValueError(
                    f"[{config.source_name}] File too small: {file_size:,} bytes "
                    f"(minimum expected: {config.min_file_size_bytes:,} bytes). "
                    f"Possible truncated or empty download."
                )

            # If the download is a ZIP, extract the inner GIS file
            if zipfile.is_zipfile(dest_path):
                log.info(f"[{config.source_name}] Downloaded file is a ZIP — extracting...")
                with zipfile.ZipFile(dest_path) as zf:
                    inner_names = zf.namelist()
                    log.info(f"[{config.source_name}] ZIP contents: {inner_names}")

                    matches = [
                        n for n in inner_names
                        if n.lower().endswith(f".{config.expected_format}")
                    ]
                    if not matches:
                        raise ValueError(
                            f"[{config.source_name}] No .{config.expected_format} file found inside ZIP. "
                            f"Contents: {inner_names}"
                        )
                    if len(matches) > 1:
                        log.warning(
                            f"[{config.source_name}] Multiple .{config.expected_format} files in ZIP, "
                            f"using first: {matches[0]}"
                        )

                    inner_name = matches[0]
                    zf.extract(inner_name, temp_dir)
                    extracted_path = temp_dir / inner_name
                    log.info(f"[{config.source_name}] Extracted → {extracted_path}")

                dest_path.unlink()  # remove the zip, keep only the extracted file
                dest_path = extracted_path

            filename = dest_path.name
            return {
                "local_path": str(dest_path),
                "temp_dir": str(temp_dir),
                "filename": filename,
                "version": version,
                "file_size_bytes": file_size,
                "sha256": sha256.hexdigest(),
            }

        # ------------------------------------------------------------------
        # Task 3: Validate GIS file
        # ------------------------------------------------------------------

        @task()
        def validate_gis_file(download_info: dict) -> dict:
            """
            Opens the file with pyogrio and performs sanity checks:

            - Can the file be opened at all?
            - Are the expected layers present?
            - Is the CRS what we expect? (warning only — not a hard fail,
              since CRS mismatches are fixable in silver via ST_Transform)
            - Are feature counts within the expected range?

            Returns a validation report with layer-level metadata.
            This report is the primary output for understanding the data
            before designing the bronze schema.

            Uses pyogrio (bundles its own GDAL wheels) instead of fiona to
            avoid system GDAL compilation issues inside Docker.
            """
            import pyogrio
            from pyproj import CRS

            local_path = download_info["local_path"]
            version = download_info["version"]
            expected_layers = _resolve_layers(config, version)

            log.info(f"[{config.source_name}] Validating: {local_path}")

            # -- List layers --
            try:
                # pyogrio.list_layers returns an ndarray of [name, geometry_type] pairs
                raw_layers = pyogrio.list_layers(local_path)
                available_layers = [row[0] for row in raw_layers]
            except Exception as exc:
                raise RuntimeError(
                    f"[{config.source_name}] pyogrio could not open file: {exc}"
                ) from exc

            log.info(f"[{config.source_name}] Layers found: {available_layers}")

            # -- Assert expected layers --
            if expected_layers:
                missing = [l for l in expected_layers if l not in available_layers]
                if missing:
                    raise ValueError(
                        f"[{config.source_name}] Missing expected layers: {missing}. "
                        f"Available: {available_layers}. "
                        f"Layer names may have changed in this release — "
                        f"update layer_name_fn or expected_layers in the config."
                    )

            # -- Per-layer inspection --
            # pyogrio.read_info() reads metadata without loading geometries into memory.
            layer_reports: dict = {}
            for layer_name in available_layers:
                info = pyogrio.read_info(local_path, layer=layer_name)

                feature_count = info.get("features", -1)
                geometry_type = info.get("geometry_type", "unknown")
                field_names = list(info.get("fields", []))
                field_dtypes = list(info.get("dtypes", []))
                field_types = dict(zip(field_names, field_dtypes))

                # Parse EPSG from WKT CRS string
                crs_wkt = info.get("crs")
                crs_epsg = None
                if crs_wkt:
                    try:
                        crs_epsg = CRS.from_wkt(crs_wkt).to_epsg()
                    except Exception:
                        log.warning(f"[{config.source_name}] Could not parse EPSG from CRS WKT.")

                # CRS check — warning only, not a hard failure
                if config.expected_crs_epsg and crs_epsg != config.expected_crs_epsg:
                    log.warning(
                        f"[{config.source_name}] Layer '{layer_name}' CRS mismatch: "
                        f"expected EPSG:{config.expected_crs_epsg}, got EPSG:{crs_epsg}. "
                        f"Silver model will need ST_Transform."
                    )

                # Feature count check — hard failure, but only for expected layers.
                # Auxiliary layers (NUTS boundaries, style tables, edge layers) are
                # logged but not validated against the configured range.
                if (
                    feature_count != -1
                    and (not expected_layers or layer_name in expected_layers)
                    and not (config.min_feature_count <= feature_count <= config.max_feature_count)
                ):
                    raise ValueError(
                        f"[{config.source_name}] Layer '{layer_name}' has {feature_count} features, "
                        f"outside expected range "
                        f"[{config.min_feature_count}, {config.max_feature_count}]. "
                        f"Possible incomplete download or wrong release."
                    )

                layer_reports[layer_name] = {
                    "feature_count": feature_count,
                    "crs_epsg": crs_epsg,
                    "geometry_type": geometry_type,
                    "field_types": field_types,      # column name → numpy dtype string
                }
                log.info(
                    f"[{config.source_name}] Layer '{layer_name}': "
                    f"{feature_count} features | EPSG:{crs_epsg} | {geometry_type}"
                )
                log.info(
                    f"[{config.source_name}]   Fields: {field_names}"
                )

            log.info(f"[{config.source_name}] Validation passed.")
            return {
                "available_layers": available_layers,
                "expected_layers": expected_layers,
                "layer_reports": layer_reports,
                "validation_passed": True,
            }

        # ------------------------------------------------------------------
        # Task 4: Upload to MinIO
        # ------------------------------------------------------------------

        @task()
        def upload_to_minio(download_info: dict, validation_report: dict) -> dict:
            """
            Uploads the raw file to MinIO.

            Path structure:
                s3://{bucket}/{prefix}/{version}/{filename}

            Where version is resolved from config or dag_run.conf.

            The SHA-256 hash is stored as object metadata so files can be
            verified later without re-downloading.
            """
            from minio import Minio
            from airflow.models import Variable

            local_path = Path(download_info["local_path"])
            version = download_info["version"]
            ingest_ts = datetime.utcnow()

            object_name = f"{config.minio_prefix}/{version}/{download_info['filename']}"

            endpoint = Variable.get("MINIO_ENDPOINT", default_var="localhost:9000")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")

            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            if not client.bucket_exists(config.minio_bucket):
                client.make_bucket(config.minio_bucket)
                log.info(f"[{config.source_name}] Created MinIO bucket: {config.minio_bucket}")

            client.fput_object(
                bucket_name=config.minio_bucket,
                object_name=object_name,
                file_path=str(local_path),
                metadata={
                    "x-amz-meta-source": config.source_name,
                    "x-amz-meta-version": version,
                    "x-amz-meta-sha256": download_info["sha256"],
                    "x-amz-meta-ingested-at": ingest_ts.isoformat(),
                },
            )

            minio_uri = f"s3://{config.minio_bucket}/{object_name}"
            log.info(f"[{config.source_name}] Uploaded → {minio_uri}")

            return {
                "minio_uri": minio_uri,
                "object_name": object_name,
                "bucket": config.minio_bucket,
                "version": version,
                "sha256": download_info["sha256"],
                "file_size_bytes": download_info["file_size_bytes"],
                "ingested_at": ingest_ts.isoformat(),
            }

        # ------------------------------------------------------------------
        # Task 5a: Cleanup temp directory
        # ------------------------------------------------------------------

        @task()
        def cleanup_temp(download_info: dict, upload_info: dict):
            """Removes the local temp directory after a successful MinIO upload.
            Depends on upload_info to ensure cleanup only runs after upload completes."""
            temp_dir = download_info.get("temp_dir")
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
                log.info(f"[{config.source_name}] Cleaned up temp dir: {temp_dir}")

        # ------------------------------------------------------------------
        # Task 5b: Log run metadata
        # ------------------------------------------------------------------

        @task()
        def log_run_metadata(upload_info: dict, validation_report: dict):
            """
            Logs a structured summary of the ingestion run.

            In production this would INSERT a row into metadata.pipeline_runs.
            That table doesn't exist yet — structured logging is sufficient
            until the metadata schema is set up alongside the bronze layer.
            """
            log.info(f"{'=' * 60}")
            log.info(f"GIS INGESTION COMPLETE — {config.source_name.upper()}")
            log.info(f"{'=' * 60}")
            log.info(f"  MinIO URI    : {upload_info['minio_uri']}")
            log.info(f"  Version      : {upload_info['version']}")
            log.info(f"  File size    : {upload_info['file_size_bytes']:,} bytes")
            log.info(f"  SHA-256      : {upload_info['sha256']}")
            log.info(f"  Ingested at  : {upload_info['ingested_at']}")
            log.info(f"  Layers found : {validation_report['available_layers']}")
            log.info("")
            for layer, report in validation_report["layer_reports"].items():
                log.info(f"  [{layer}]")
                log.info(f"    Features  : {report['feature_count']:,}")
                log.info(f"    CRS       : EPSG:{report['crs_epsg']}")
                log.info(f"    Geometry  : {report['geometry_type']}")
                log.info(f"    Fields    : {list(report['field_types'].keys())}")
            log.info(f"{'=' * 60}")
            log.info("Next step: explore raw file from MinIO, then design bronze DDL.")

        # ------------------------------------------------------------------
        # Wire the task graph
        # ------------------------------------------------------------------

        source_info = check_source_availability()
        download_info = download_file(source_info)
        validation_report = validate_gis_file(download_info)
        upload_info = upload_to_minio(download_info, validation_report)
        cleanup_temp(download_info, upload_info)   # upload_info dep ensures cleanup runs after upload
        log_run_metadata(upload_info, validation_report)

    return gis_ingestion_dag()
