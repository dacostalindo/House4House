"""
Generate an HTML survey for external evaluators to validate Claude Vision classifications.

Reads the sample CSV and produces a self-contained HTML file with:
- 3 property images per listing (clickable)
- Radio buttons for condition, finish quality, and render detection
- Hidden ground truth (Claude's labels) in a JSON block for later comparison
- Export button to download evaluator responses as JSON
"""

import json
import html as html_lib
from pathlib import Path

SAMPLE_FILE = Path("/tmp/survey_sample.csv")
OUTPUT_FILE = Path(__file__).parent / "validation_survey.html"

def parse_sample():
    listings = []
    for line in SAMPLE_FILE.read_text().strip().split("\n"):
        parts = line.split("|||")
        if len(parts) < 15:
            continue
        listings.append({
            "property_id": parts[0],
            "cv_condition": parts[1],
            "cv_condition_conf": parts[2],
            "cv_finish": parts[3],
            "cv_finish_conf": parts[4],
            "cv_is_render": parts[5] == "t",
            "cv_render_conf": parts[6],
            "img1": parts[7],
            "img2": parts[8],
            "img3": parts[9],
            "tag1": parts[10],
            "tag2": parts[11],
            "tag3": parts[12],
            "listing_url": parts[13],
            "idealista_condition": parts[14],
        })
    return listings

def generate_html(listings):
    cards_html = ""
    ground_truth = {}

    for i, L in enumerate(listings):
        pid = L["property_id"]
        ground_truth[pid] = {
            "cv_condition": L["cv_condition"],
            "cv_condition_conf": L["cv_condition_conf"],
            "cv_finish": L["cv_finish"],
            "cv_finish_conf": L["cv_finish_conf"],
            "cv_is_render": L["cv_is_render"],
            "cv_render_conf": L["cv_render_conf"],
            "idealista_condition": L["idealista_condition"],
        }

        imgs = []
        for url, tag in [(L["img1"], L["tag1"]), (L["img2"], L["tag2"]), (L["img3"], L["tag3"])]:
            if url:
                imgs.append(f'<div class="img-col"><a href="{html_lib.escape(url)}" target="_blank"><img src="{html_lib.escape(url)}" loading="lazy"></a><span class="tag">{html_lib.escape(tag)}</span></div>')

        cards_html += f"""
    <div class="card" id="card-{pid}" data-pid="{pid}">
      <div class="card-header">
        <span class="num">#{i+1}</span>
        <a href="{html_lib.escape(L['listing_url'])}" target="_blank" class="listing-link">Ver anuncio completo &rarr;</a>
      </div>
      <div class="images">{''.join(imgs)}</div>
      <div class="questions">
        <div class="q-group">
          <label class="q-label">1. Estado de conservacao do imovel</label>
          <div class="options">
            <label><input type="radio" name="cond-{pid}" value="needs_renovation"> <strong>Precisa de obras</strong><br><small>Qualquer nivel de renovacao necessario — desde atualizacoes cosmeticas a obras estruturais</small></label>
            <label><input type="radio" name="cond-{pid}" value="habitable"> <strong>Habitavel</strong><br><small>Funcional e habitavel no estado atual, sem danos visiveis, mas nao foi atualizado recentemente</small></label>
            <label><input type="radio" name="cond-{pid}" value="renovated"> <strong>Renovado</strong><br><small>Materiais claramente novos ou recentemente atualizados — pintura fresca, equipamentos modernos</small></label>
            <label><input type="radio" name="cond-{pid}" value="uncertain"> <strong>Incerto</strong><br><small>Nao e possivel determinar a partir destas imagens</small></label>
          </div>
        </div>
        <div class="q-group">
          <label class="q-label">2. Qualidade dos acabamentos interiores</label>
          <div class="options">
            <label><input type="radio" name="finish-{pid}" value="basic"> <strong>Basico</strong><br><small>Chao em laminado/vinilico, azulejos basicos, materiais baratos, sem marca</small></label>
            <label><input type="radio" name="finish-{pid}" value="standard"> <strong>Standard</strong><br><small>Ceramica/laminado, cozinha standard, casa de banho funcional, decente mas sem destaque</small></label>
            <label><input type="radio" name="finish-{pid}" value="premium"> <strong>Premium</strong><br><small>Chao em madeira/marmore, cozinha de qualidade (pedra, eletrodomesticos de marca), casa de banho moderna</small></label>
            <label><input type="radio" name="finish-{pid}" value="uncertain"> <strong>Incerto</strong><br><small>Nao e possivel determinar a partir destas imagens</small></label>
          </div>
        </div>
        <div class="q-group">
          <label class="q-label">3. Estas imagens sao fotografias reais ou renders 3D/CGI?</label>
          <div class="options">
            <label><input type="radio" name="render-{pid}" value="real"> <strong>Fotografias reais</strong></label>
            <label><input type="radio" name="render-{pid}" value="render"> <strong>Renders 3D / CGI</strong></label>
            <label><input type="radio" name="render-{pid}" value="mixed"> <strong>Mistura de ambos</strong></label>
            <label><input type="radio" name="render-{pid}" value="uncertain"> <strong>Incerto</strong></label>
          </div>
        </div>
        <div class="q-group">
          <label class="q-label">4. Observacoes (opcional)</label>
          <textarea name="notes-{pid}" rows="2" placeholder="Qualquer observacao sobre este imovel..."></textarea>
        </div>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Questionario de Classificacao de Imoveis</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; line-height: 1.5; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
  .header {{ background: #1a1a2e; color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
  .header p {{ opacity: 0.85; font-size: 14px; }}
  .header .stats {{ margin-top: 16px; display: flex; gap: 20px; }}
  .header .stat {{ background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 8px; font-size: 13px; }}
  .progress-bar {{ background: #e0e0e0; border-radius: 8px; height: 8px; margin-bottom: 24px; overflow: hidden; }}
  .progress-fill {{ background: #4CAF50; height: 100%; width: 0%; transition: width 0.3s; }}
  .progress-text {{ text-align: center; font-size: 13px; color: #666; margin-bottom: 16px; }}
  .card {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 24px; overflow: hidden; }}
  .card-header {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; background: #f8f9fa; border-bottom: 1px solid #eee; }}
  .num {{ font-weight: 700; color: #1a1a2e; font-size: 16px; }}
  .listing-link {{ color: #2196F3; text-decoration: none; font-size: 13px; }}
  .listing-link:hover {{ text-decoration: underline; }}
  .images {{ display: flex; gap: 8px; padding: 16px; background: #fafafa; }}
  .img-col {{ flex: 1; text-align: center; }}
  .img-col img {{ width: 100%; border-radius: 8px; cursor: pointer; transition: transform 0.2s; }}
  .img-col img:hover {{ transform: scale(1.02); }}
  .tag {{ display: inline-block; margin-top: 6px; padding: 2px 10px; background: #e8e8e8; border-radius: 12px; font-size: 11px; color: #666; }}
  .questions {{ padding: 20px; }}
  .q-group {{ margin-bottom: 18px; }}
  .q-label {{ font-weight: 600; font-size: 14px; margin-bottom: 8px; display: block; color: #1a1a2e; }}
  .options {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .options label {{ display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; background: #f8f9fa; border-radius: 8px; cursor: pointer; font-size: 13px; border: 2px solid transparent; transition: all 0.15s; }}
  .options label:hover {{ background: #eef; }}
  .options label:has(input:checked) {{ border-color: #2196F3; background: #e3f2fd; }}
  .options input[type="radio"] {{ margin-top: 3px; }}
  .options small {{ color: #888; font-size: 11px; }}
  textarea {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-family: inherit; font-size: 13px; resize: vertical; }}
  .actions {{ text-align: center; padding: 30px; }}
  .btn {{ padding: 14px 32px; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
  .btn-primary {{ background: #1a1a2e; color: white; }}
  .btn-primary:hover {{ background: #2a2a4e; }}
  .btn-secondary {{ background: #e0e0e0; color: #333; margin-left: 12px; }}
  .completed {{ border-left: 4px solid #4CAF50; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Questionario de Classificacao de Imoveis</h1>
    <p>Por favor, avalie cada imovel com base nas 3 imagens apresentadas. Clique em qualquer imagem para ver em tamanho real. Clique em "Ver anuncio completo" para ver todas as fotos no Idealista.</p>
    <div class="stats">
      <div class="stat">{len(listings)} imoveis para avaliar</div>
      <div class="stat">3 perguntas por imovel</div>
      <div class="stat">~15-20 min estimados</div>
    </div>
  </div>

  <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
  <div class="progress-text" id="progress-text">0 / {len(listings)} concluidos</div>

  {cards_html}

  <div class="actions">
    <button class="btn btn-primary" onclick="exportResponses()">Exportar Respostas (JSON)</button>
    <button class="btn btn-secondary" onclick="exportCSV()">Exportar Respostas (CSV)</button>
  </div>
</div>

<!-- Ground truth (hidden) — DO NOT share with evaluator -->
<script id="ground-truth" type="application/json">{json.dumps(ground_truth)}</script>

<script>
const TOTAL = {len(listings)};
const pids = {json.dumps([L["property_id"] for L in listings])};

function updateProgress() {{
  let done = 0;
  pids.forEach(pid => {{
    const cond = document.querySelector(`input[name="cond-${{pid}}"]:checked`);
    const finish = document.querySelector(`input[name="finish-${{pid}}"]:checked`);
    const render = document.querySelector(`input[name="render-${{pid}}"]:checked`);
    const card = document.getElementById(`card-${{pid}}`);
    if (cond && finish && render) {{
      done++;
      card.classList.add('completed');
    }} else {{
      card.classList.remove('completed');
    }}
  }});
  document.getElementById('progress-fill').style.width = (100 * done / TOTAL) + '%';
  document.getElementById('progress-text').textContent = done + ' / ' + TOTAL + ' concluidos';
}}

document.querySelectorAll('input[type="radio"]').forEach(r => r.addEventListener('change', updateProgress));

function collectResponses() {{
  const responses = {{}};
  pids.forEach(pid => {{
    const cond = document.querySelector(`input[name="cond-${{pid}}"]:checked`);
    const finish = document.querySelector(`input[name="finish-${{pid}}"]:checked`);
    const render = document.querySelector(`input[name="render-${{pid}}"]:checked`);
    const notes = document.querySelector(`textarea[name="notes-${{pid}}"]`);
    responses[pid] = {{
      condition: cond ? cond.value : null,
      finish_quality: finish ? finish.value : null,
      is_render: render ? render.value : null,
      notes: notes ? notes.value : '',
    }};
  }});
  return responses;
}}

function exportResponses() {{
  const data = {{
    evaluator: prompt('O seu nome ou identificador:') || 'anonimo',
    timestamp: new Date().toISOString(),
    responses: collectResponses(),
  }};
  const blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'survey_responses_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
}}

function exportCSV() {{
  const responses = collectResponses();
  let csv = 'property_id,condition,finish_quality,is_render,notes\\n';
  pids.forEach(pid => {{
    const r = responses[pid];
    csv += `${{pid}},${{r.condition || ''}},${{r.finish_quality || ''}},${{r.is_render || ''}},"${{(r.notes || '').replace(/"/g, '""')}}"\\n`;
  }});
  const blob = new Blob([csv], {{type: 'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'survey_responses_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}}
</script>
</body>
</html>"""


def main():
    listings = parse_sample()
    print(f"Parsed {len(listings)} listings")
    html = generate_html(listings)
    OUTPUT_FILE.write_text(html)
    print(f"Survey written to {OUTPUT_FILE}")
    print(f"Ground truth embedded in hidden <script> tag (50 listings)")


if __name__ == "__main__":
    main()
