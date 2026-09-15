from __future__ import annotations

import base64
import html
import math
from pathlib import Path

from .image_tools import annotation_is_visible, render_step_image, view_box_normalized
from .models import RichText, TutorialProject


NAVIGATION_SCRIPT = r"""
(function () {
  "use strict";
  document.documentElement.classList.add("js-ready");
  var steps = Array.prototype.slice.call(document.querySelectorAll(".step[data-step-index]"));
  if (!steps.length) return;

  var guideHeader = document.querySelector(".guide-header");
  var rail = document.querySelector(".reading-rail");
  var railScroll = document.querySelector(".rail-track-scroll");
  var railLabel = document.getElementById("rail-progress-label");
  var railPercent = document.getElementById("rail-progress-percent");
  var railBar = document.querySelector(".rail-progressbar");
  var railFill = document.querySelector(".rail-line-fill");
  var railLinks = Array.prototype.slice.call(document.querySelectorAll(".rail-step-link"));
  var mobile = document.querySelector(".mobile-progress");
  var mobileLabel = document.getElementById("mobile-progress-label");
  var mobileTitle = document.getElementById("mobile-progress-title");
  var mobilePercent = document.getElementById("mobile-progress-percent");
  var mobileBar = document.querySelector(".mobile-progressbar");
  var mobileFill = document.querySelector(".mobile-progress-fill");
  var previousLink = document.querySelector(".mobile-previous");
  var nextLink = document.querySelector(".mobile-next");
  var nextText = document.querySelector(".mobile-next-text");
  var stepLinks = Array.prototype.slice.call(document.querySelectorAll('.index-link,.rail-step-link'));
  var tooltip = document.querySelector(".rail-tooltip");
  var tooltipStep = document.querySelector(".rail-tooltip-step");
  var tooltipTitle = document.querySelector(".rail-tooltip-title");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var activeIndex = -1;
  var scheduled = false;

  function setDisabled(link, disabled) {
    if (!link) return;
    link.classList.toggle("is-disabled", disabled);
    link.setAttribute("aria-disabled", disabled ? "true" : "false");
    link.tabIndex = disabled ? -1 : 0;
  }

  function keepRailLinkVisible(link) {
    if (!railScroll || !link) return;
    var top = link.offsetTop;
    var bottom = top + link.offsetHeight;
    var visibleTop = railScroll.scrollTop;
    var visibleBottom = visibleTop + railScroll.clientHeight;
    if (top < visibleTop) railScroll.scrollTo({ top: Math.max(0, top - 8), behavior: reducedMotion ? "auto" : "smooth" });
    else if (bottom > visibleBottom) railScroll.scrollTo({ top: bottom - railScroll.clientHeight + 8, behavior: reducedMotion ? "auto" : "smooth" });
  }

  function setActive(index) {
    index = Math.max(0, Math.min(steps.length - 1, index));
    if (index === activeIndex) return;
    activeIndex = index;
    var current = steps[index];
    var titleNode = current.querySelector(".step-title");
    var title = titleNode ? titleNode.textContent.trim() : "";
    var percent = Math.round(((index + 1) / steps.length) * 100);
    var label = "Paso " + (index + 1) + " de " + steps.length;
    railLabel.textContent = label;
    railPercent.textContent = percent + "%";
    railBar.setAttribute("aria-valuenow", String(percent));
    railFill.style.height = percent + "%";
    mobileLabel.textContent = label;
    mobileTitle.textContent = title;
    mobilePercent.textContent = percent + "%";
    mobileBar.setAttribute("aria-valuenow", String(percent));
    mobileFill.style.width = percent + "%";
    steps.forEach(function (step, position) {
      step.classList.toggle("is-active", position === index);
    });
    stepLinks.forEach(function (link) {
      if (link.getAttribute("href") === "#paso-" + (index + 1)) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    keepRailLinkVisible(railLinks[index]);
    previousLink.setAttribute("href", index > 0 ? "#paso-" + index : "#inicio");
    setDisabled(previousLink, index === 0);
    nextLink.setAttribute("href", index < steps.length - 1 ? "#paso-" + (index + 2) : "#fin");
    nextLink.setAttribute("aria-label", index < steps.length - 1 ? "Ir al paso siguiente" : "Ir al final del tutorial");
    nextText.textContent = index < steps.length - 1 ? "Siguiente" : "Final";
  }

  function refresh() {
    scheduled = false;
    var marker = window.innerHeight * 0.34;
    var index = 0;
    steps.forEach(function (step, position) {
      if (step.getBoundingClientRect().top <= marker) index = position;
    });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
      index = steps.length - 1;
    }
    setActive(index);
    var pastHeader = guideHeader.getBoundingClientRect().bottom < 64;
    rail.classList.toggle("is-visible", pastHeader);
    mobile.classList.toggle("is-visible", pastHeader);
  }

  function scheduleRefresh() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(refresh);
  }

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(scheduleRefresh, {
      rootMargin: "-20% 0px -60% 0px",
      threshold: [0, 0.01, 0.5]
    });
    steps.forEach(function (step) { observer.observe(step); });
  }
  window.addEventListener("scroll", scheduleRefresh, { passive: true });
  window.addEventListener("resize", scheduleRefresh);
  document.querySelectorAll("a.is-disabled").forEach(function (link) {
    link.addEventListener("click", function (event) {
      if (link.classList.contains("is-disabled")) event.preventDefault();
    });
  });
  railLinks.forEach(function (link, position) {
    function showTooltip() {
      if (!tooltip) return;
      var rect = link.getBoundingClientRect();
      var titleNode = link.querySelector(".rail-link-title");
      tooltipStep.textContent = "Paso " + (position + 1) + " de " + steps.length;
      tooltipTitle.textContent = titleNode ? titleNode.textContent : "";
      tooltip.style.top = Math.max(12, Math.min(window.innerHeight - tooltip.offsetHeight - 12, rect.top + rect.height / 2 - tooltip.offsetHeight / 2)) + "px";
      tooltip.classList.add("is-visible");
    }
    function hideTooltip() { if (tooltip) tooltip.classList.remove("is-visible"); }
    link.addEventListener("mouseenter", showTooltip);
    link.addEventListener("mouseleave", hideTooltip);
    link.addEventListener("focus", showTooltip);
    link.addEventListener("blur", hideTooltip);
  });
  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener("click", function () {
      if (link.classList.contains("is-disabled")) return;
      var target = document.getElementById(link.getAttribute("href").slice(1));
      if (!target) return;
      window.setTimeout(function () { target.focus({ preventScroll: true }); }, reducedMotion ? 0 : 350);
    });
  });
  refresh();
}());
""".strip()


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def render_rich_text(value: RichText) -> str:
    """Convierte únicamente las marcas estructuradas admitidas a HTML seguro."""

    value.normalize()
    boundaries = {0, len(value.text)}
    for mark in value.marks:
        boundaries.update((mark.start, mark.end))
    points = sorted(boundaries)
    parts: list[str] = []
    for start, end in zip(points, points[1:]):
        if start == end:
            continue
        segment = _e(value.text[start:end]).replace("\n", "<br>")
        active = [mark for mark in value.marks if mark.start <= start and mark.end >= end]
        if any(mark.type == "bold" for mark in active):
            segment = f"<strong>{segment}</strong>"
        links = [mark for mark in active if mark.type == "link" and mark.url]
        if links:
            url = links[0].url or ""
            extra = ' target="_blank" rel="noopener noreferrer"' if url.startswith(("http://", "https://")) else ""
            segment = f'<a href="{_e(url)}"{extra}>{segment}</a>'
        parts.append(segment)
    return "".join(parts)


def collect_export_warnings(project: TutorialProject) -> list[str]:
    warnings: list[str] = []
    for index, step in enumerate(project.steps, start=1):
        name = step.title.strip() or f"Paso {index}"
        if not step.instruction.text.strip():
            warnings.append(f"{name}: no tiene instrucción.")
        if not step.visual_reviewed:
            warnings.append(f"{name}: no tiene revisión visual confirmada.")
        view_box = view_box_normalized(
            step.image_png, step.crop, step.focus_x, step.focus_y, step.zoom
        )
        outside = [
            annotation
            for annotation in step.annotations
            if not annotation_is_visible(annotation, view_box)
        ]
        if outside:
            warnings.append(
                f"{name}: {len(outside)} anotación(es) quedan fuera del recorte o zoom."
            )
    return warnings


def _step_word(total: int) -> str:
    return "paso" if total == 1 else "pasos"


def _estimated_minutes(total: int) -> int:
    return max(1, math.ceil(total * 15 / 60)) if total else 0


def _contrast_text_color(color: str) -> str:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    white_contrast = 1.05 / (luminance + 0.05)
    dark_contrast = (luminance + 0.05) / 0.057
    return "#ffffff" if white_contrast >= dark_contrast else "#101828"


def build_html(project: TutorialProject) -> str:
    project.normalize()
    title = project.title.strip() or "Tutorial"
    total = len(project.steps)
    step_word = _step_word(total)
    minutes = _estimated_minutes(total)
    minute_word = "minuto" if minutes == 1 else "minutos"
    accent_ink = _contrast_text_color(project.accent_color)
    description_html = ""
    if project.description.text.strip():
        description_html = (
            f'<p class="guide-description">'
            f'{render_rich_text(project.description)}</p>'
        )

    logo_html = ""
    if project.logo_png:
        logo = base64.b64encode(project.logo_png).decode("ascii")
        logo_html = f'<img class="brand-logo" src="data:image/png;base64,{logo}" alt="">'
    brand_name = _e(project.brand_name.strip())
    brand_html = ""
    if logo_html or brand_name:
        brand_html = f'<div class="brand">{logo_html}<span>{brand_name}</span></div>'

    cards: list[str] = []
    index_items: list[str] = []
    rail_items: list[str] = []
    for index, step in enumerate(project.steps, start=1):
        image_webp = render_step_image(
            step.image_png,
            step.focus_x,
            step.focus_y,
            step.zoom,
            crop=step.crop,
            annotations=step.annotations,
            accent_color=project.accent_color,
        )
        encoded = base64.b64encode(image_webp).decode("ascii")
        step_title = step.title.strip() or f"Paso {index}"
        instruction = render_rich_text(step.instruction)
        instruction_html = f'<p class="instruction">{instruction}</p>' if instruction else ""
        index_items.append(
            f'<li><a class="index-link" href="#paso-{index}"><span class="index-number">{index}</span>'
            f'<span>{_e(step_title)}</span></a></li>'
        )
        rail_items.append(
            f'<li><a class="rail-step-link" href="#paso-{index}" '
            f'aria-label="Paso {index} de {total}: {_e(step_title)}">'
            f'<span class="rail-dot" aria-hidden="true"></span>'
            f'<span class="rail-link-title visually-hidden">{_e(step_title)}</span></a></li>'
        )
        cards.append(
            f"""<article class="step" id="paso-{index}" data-step-index="{index}" tabindex="-1">
  <header class="step-header"><span class="number">{index}</span><div class="step-heading"><span class="step-position">Paso {index} de {total}</span><h2 class="step-title">{_e(step_title)}</h2></div></header>
  {instruction_html}
  <img class="step-image" src="data:image/webp;base64,{encoded}" alt="{_e(step_title)}" loading="lazy">
</article>"""
        )

    if total:
        index_html = (
            f'<details class="tutorial-index"><summary>Ver los {total} {step_word}</summary>'
            f'<nav aria-label="Índice del tutorial"><ol>{"".join(index_items)}</ol></nav></details>'
        )
        initial_percent = round(100 / total)
        hero_actions = (
            f'<div class="hero-actions"><a class="start-button" href="#paso-1">'
            f'<span>Comenzar tutorial</span><span aria-hidden="true">↓</span></a>{index_html}</div>'
        )
        metrics_html = f"""<div class="hero-metrics" role="list" aria-label="Resumen del tutorial">
  <div class="hero-metric" role="listitem"><span class="metric-value">{total}</span><span class="metric-label">{step_word}</span></div>
  <div class="metric-divider" aria-hidden="true"></div>
  <div class="hero-metric" role="listitem"><span class="metric-value">{minutes} min</span><span class="metric-label">Tiempo estimado</span></div>
</div>"""
        navigation_html = f"""<nav class="reading-rail" aria-label="Progreso y navegación del tutorial">
  <div class="rail-summary" role="status" aria-live="polite" aria-atomic="true">
    <span class="rail-eyebrow">Progreso</span><strong id="rail-progress-label">Paso 1 de {total}</strong><span id="rail-progress-percent">{initial_percent}%</span>
  </div>
  <div class="rail-track-scroll"><div class="rail-track">
    <div class="rail-progressbar" role="progressbar" aria-labelledby="rail-progress-label" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{initial_percent}"><span class="rail-line-fill" style="height:{initial_percent}%"></span></div>
    <ol class="rail-step-list">{"".join(rail_items)}</ol>
  </div></div>
  <a class="rail-top" href="#inicio"><span aria-hidden="true">↑</span><span>Volver arriba</span></a>
</nav>
<div class="rail-tooltip" aria-hidden="true"><strong class="rail-tooltip-step"></strong><span class="rail-tooltip-title"></span></div>
<nav class="mobile-progress" aria-label="Progreso y navegación del tutorial">
  <a class="mobile-control mobile-previous is-disabled" href="#inicio" aria-label="Ir al paso anterior" aria-disabled="true" tabindex="-1"><span aria-hidden="true">←</span><span>Anterior</span></a>
  <div class="mobile-summary" role="status" aria-live="polite" aria-atomic="true"><div class="mobile-copy"><strong id="mobile-progress-label">Paso 1 de {total}</strong><span id="mobile-progress-percent">{initial_percent}%</span></div><span id="mobile-progress-title">{_e(project.steps[0].title.strip() or 'Paso 1')}</span><div class="mobile-progressbar" role="progressbar" aria-labelledby="mobile-progress-label" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{initial_percent}"><span class="mobile-progress-fill" style="width:{initial_percent}%"></span></div></div>
  <a class="mobile-control mobile-next" href="{'#paso-2' if total > 1 else '#fin'}" aria-label="{'Ir al paso siguiente' if total > 1 else 'Ir al final del tutorial'}"><span class="mobile-next-text">{'Siguiente' if total > 1 else 'Final'}</span><span aria-hidden="true">→</span></a>
</nav>"""
        completion_html = f"""<section class="completion" id="fin" aria-labelledby="completion-title" tabindex="-1">
  <span class="completion-icon" aria-hidden="true">✓</span>
  <h2 id="completion-title">Tutorial completado</h2>
  <p>Has llegado al final de {total} {step_word}.</p>
  <a class="back-top" href="#inicio">Volver arriba</a>
</section>"""
        script_html = f"<script>\n{NAVIGATION_SCRIPT}\n</script>"
    else:
        hero_actions = '<p class="hero-empty">Este tutorial aún no contiene pasos</p>'
        metrics_html = f"""<div class="hero-metrics" role="list" aria-label="Resumen del tutorial">
  <div class="hero-metric" role="listitem"><span class="metric-value">0</span><span class="metric-label">pasos</span></div>
</div>"""
        navigation_html = ""
        completion_html = ""
        script_html = ""

    body_class = ' class="has-navigation"' if total else ""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>
:root {{ color-scheme:light; --ink:#172033; --muted:#5d6677; --accent:{project.accent_color}; --accent-ink:{accent_ink}; --paper:#fff; --bg:#f3f5f8; }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; overflow-x:hidden; background:var(--bg); color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ width:min(1040px, calc(100% - 32px)); margin:32px auto 80px; }}
.visually-hidden {{ position:absolute!important; width:1px!important; height:1px!important; padding:0!important; margin:-1px!important; overflow:hidden!important; clip:rect(0,0,0,0)!important; white-space:nowrap!important; border:0!important; }}
.guide-header {{ position:relative; isolation:isolate; overflow:visible; min-height:520px; display:flex; flex-direction:column; justify-content:center; margin-bottom:46px; padding:clamp(38px,7vw,82px); border:1px solid rgba(255,255,255,.9); border-radius:30px; background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(255,255,255,.86)); box-shadow:0 24px 70px rgba(23,32,51,.09); }}
.guide-header::before,.guide-header::after {{ content:""; position:absolute; z-index:-1; border-radius:50%; pointer-events:none; }}
.guide-header::before {{ width:300px; height:300px; right:-90px; top:-120px; background:color-mix(in srgb,var(--accent) 16%,transparent); }}
.guide-header::after {{ width:190px; height:190px; right:110px; bottom:-110px; background:color-mix(in srgb,var(--accent) 8%,transparent); }}
.hero-top {{ display:flex; align-items:center; justify-content:space-between; gap:18px; margin-bottom:32px; }}
.brand {{ display:flex; align-items:center; gap:12px; min-height:34px; color:var(--muted); font-weight:750; letter-spacing:.02em; }}
.brand-logo {{ width:auto; max-width:160px; height:42px; object-fit:contain; }}
.guide-kicker {{ display:inline-flex; align-items:center; width:max-content; padding:7px 11px; border:1px solid color-mix(in srgb,var(--accent) 28%,#dce2ea); border-radius:999px; background:color-mix(in srgb,var(--accent) 8%,white); color:color-mix(in srgb,var(--accent) 68%,#172033); font-size:.76rem; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
.guide-kicker::before {{ content:""; width:7px; height:7px; margin-right:7px; border-radius:50%; background:var(--accent); }}
h1 {{ max-width:850px; margin:0 0 16px; font-size:clamp(2.35rem,6vw,4.6rem); line-height:1.02; letter-spacing:-.052em; text-wrap:balance; }}
.guide-description {{ max-width:760px; margin:0; color:var(--muted); font-size:clamp(1.05rem,1.8vw,1.22rem); line-height:1.65; }}
.hero-metrics {{ display:flex; align-items:center; width:max-content; max-width:100%; margin-top:30px; padding:13px 18px; border:1px solid #e0e5ec; border-radius:16px; background:rgba(255,255,255,.74); box-shadow:0 10px 26px rgba(23,32,51,.05); }}
.hero-metric {{ display:grid; grid-template-columns:auto auto; align-items:baseline; gap:7px; }}
.metric-value {{ color:var(--ink); font-size:1.08rem; font-weight:850; }}
.metric-label {{ color:var(--muted); font-size:.86rem; }}
.metric-divider {{ width:1px; height:26px; margin:0 18px; background:#dce2ea; }}
.hero-actions {{ display:flex; align-items:flex-start; flex-wrap:wrap; gap:12px; margin-top:28px; }}
.start-button,.tutorial-index summary {{ display:inline-flex; align-items:center; justify-content:center; gap:10px; min-height:48px; padding:11px 17px; border-radius:13px; font-weight:800; text-decoration:none; cursor:pointer; user-select:none; }}
.start-button {{ border:1px solid var(--accent); background:var(--accent); color:var(--accent-ink); box-shadow:0 10px 24px color-mix(in srgb,var(--accent) 23%,transparent); }}
.start-button:hover {{ transform:translateY(-1px); box-shadow:0 13px 28px color-mix(in srgb,var(--accent) 29%,transparent); }}
.tutorial-index {{ position:relative; }}
.tutorial-index summary {{ border:1px solid #d9dfe8; background:rgba(255,255,255,.88); color:var(--ink); list-style:none; }}
.tutorial-index summary::-webkit-details-marker {{ display:none; }}
.tutorial-index summary::after {{ content:"⌄"; margin-left:3px; color:var(--muted); }}
.tutorial-index[open] summary::after {{ transform:rotate(180deg); }}
.tutorial-index nav {{ position:absolute; z-index:30; top:calc(100% + 9px); left:0; width:min(620px,calc(100vw - 48px)); max-height:min(420px,60vh); overflow:auto; padding:14px; border:1px solid #dce2ea; border-radius:16px; background:rgba(255,255,255,.98); box-shadow:0 22px 55px rgba(23,32,51,.16); backdrop-filter:blur(15px); }}
.tutorial-index ol {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 18px; margin:0; padding:0; list-style:none; }}
.tutorial-index a {{ display:flex; align-items:flex-start; gap:9px; padding:8px; border-radius:9px; color:var(--ink); text-decoration:none; }}
.tutorial-index a:hover,.tutorial-index a:focus-visible,.tutorial-index a[aria-current="step"] {{ color:var(--accent); background:#fff; outline:none; }}
.index-number {{ display:grid; place-items:center; flex:0 0 24px; height:24px; border-radius:50%; background:#e8edf4; color:var(--ink); font-size:.78rem; font-weight:800; }}
.tutorial-index a[aria-current="step"] .index-number {{ background:var(--accent); color:var(--accent-ink); }}
.hero-empty {{ width:max-content; max-width:100%; margin:28px 0 0; padding:12px 15px; border:1px solid #dde2e9; border-radius:12px; background:rgba(255,255,255,.72); color:var(--muted); font-weight:700; }}
.reading-rail {{ position:fixed; z-index:100; top:50%; right:max(18px,calc((100vw - 1250px)/2)); display:flex; flex-direction:column; width:112px; max-height:calc(100vh - 40px); padding:14px 10px 10px; border:1px solid rgba(215,222,232,.94); border-radius:22px; background:rgba(255,255,255,.94); box-shadow:0 18px 50px rgba(23,32,51,.15); backdrop-filter:blur(16px); opacity:0; transform:translate(24px,-50%); pointer-events:none; transition:opacity .2s ease,transform .2s ease; }}
.js-ready .reading-rail.is-visible {{ opacity:1; transform:translate(0,-50%); pointer-events:auto; }}
.rail-summary {{ display:grid; justify-items:center; padding:2px 2px 10px; text-align:center; }}
.rail-eyebrow {{ color:var(--muted); font-size:.66rem; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
#rail-progress-label {{ margin-top:2px; font-size:.75rem; white-space:nowrap; }}
#rail-progress-percent {{ color:var(--accent); font-size:1.15rem; font-weight:900; }}
.rail-track-scroll {{ flex:1 1 auto; min-height:52px; overflow-y:auto; scrollbar-width:none; overscroll-behavior:contain; }}
.rail-track-scroll::-webkit-scrollbar {{ display:none; }}
.rail-track {{ position:relative; min-height:100%; }}
.rail-progressbar {{ position:absolute; top:22px; bottom:22px; left:50%; width:3px; overflow:hidden; border-radius:99px; background:#e1e6ed; transform:translateX(-50%); }}
.rail-line-fill {{ display:block; width:100%; min-height:3px; border-radius:inherit; background:var(--accent); transition:height .2s ease; }}
.rail-step-list {{ position:relative; z-index:1; display:grid; justify-content:center; gap:2px; margin:0; padding:0; list-style:none; }}
.rail-step-link {{ position:relative; display:grid; place-items:center; width:44px; height:44px; border-radius:50%; text-decoration:none; }}
.rail-step-link:hover,.rail-step-link:focus-visible {{ background:color-mix(in srgb,var(--accent) 10%,white); outline:none; }}
.rail-dot {{ width:10px; height:10px; border:3px solid white; border-radius:50%; background:#b7c0ce; box-shadow:0 0 0 1px #aab4c2; transition:width .16s ease,height .16s ease,background .16s ease,box-shadow .16s ease; }}
.rail-step-link[aria-current="step"] .rail-dot {{ width:17px; height:17px; background:var(--accent); box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 18%,white),0 0 0 5px color-mix(in srgb,var(--accent) 44%,#aab4c2); }}
.rail-top {{ display:flex; align-items:center; justify-content:center; gap:5px; min-height:40px; margin-top:8px; border-top:1px solid #e3e7ed; color:var(--ink); font-size:.68rem; font-weight:800; text-decoration:none; }}
.rail-tooltip {{ position:fixed; z-index:110; right:max(140px,calc((100vw - 1250px)/2 + 130px)); display:grid; width:230px; padding:11px 13px; border:1px solid #dce2ea; border-radius:12px; background:#172033; color:white; box-shadow:0 14px 35px rgba(23,32,51,.2); opacity:0; transform:translateX(8px); pointer-events:none; transition:opacity .14s ease,transform .14s ease; }}
.rail-tooltip.is-visible {{ opacity:1; transform:translateX(0); }}
.rail-tooltip-step {{ color:#cbd3df; font-size:.69rem; letter-spacing:.06em; text-transform:uppercase; }}
.rail-tooltip-title {{ margin-top:2px; font-size:.84rem; line-height:1.35; }}
.mobile-progress {{ display:none; }}
.step {{ scroll-margin-top:24px; background:var(--paper); border:1px solid #e1e5eb; border-radius:20px; box-shadow:0 10px 30px rgba(28,38,58,.07); padding:24px; margin:0 0 28px; break-inside:avoid; transition:border-color .18s ease,box-shadow .18s ease; }}
.step.is-active {{ border-color:color-mix(in srgb,var(--accent) 55%,white); box-shadow:0 12px 34px rgba(28,38,58,.1),0 0 0 2px color-mix(in srgb,var(--accent) 14%,transparent); }}
.step:focus-visible {{ outline:3px solid color-mix(in srgb,var(--accent) 45%,transparent); outline-offset:3px; }}
.step-header {{ display:flex; align-items:center; gap:13px; margin-bottom:10px; }}
.number {{ display:grid; place-items:center; flex:0 0 36px; height:36px; border-radius:50%; background:var(--accent); color:var(--accent-ink); font-weight:800; }}
.step-heading {{ min-width:0; }}
.step-position {{ display:block; margin-bottom:2px; color:var(--muted); font-size:.78rem; font-weight:750; letter-spacing:.045em; text-transform:uppercase; }}
h2 {{ margin:0; font-size:1.35rem; line-height:1.25; }}
.instruction {{ color:var(--muted); margin:0 0 18px 49px; }}
.guide-description a,.instruction a {{ color:var(--accent); text-decoration:underline; text-underline-offset:2px; }}
.step-image {{ width:100%; height:auto; display:block; border-radius:12px; border:1px solid #dfe3e9; background:#eef1f5; }}
.completion {{ display:grid; justify-items:center; padding:38px 20px; margin-top:38px; text-align:center; background:var(--paper); border:1px solid #dce2ea; border-radius:18px; box-shadow:0 10px 30px rgba(28,38,58,.06); }}
.completion-icon {{ display:grid; place-items:center; width:52px; height:52px; margin-bottom:12px; border-radius:50%; background:var(--accent); color:var(--accent-ink); font-size:1.55rem; font-weight:800; }}
.completion h2 {{ font-size:1.55rem; }}
.completion p {{ margin:7px 0 18px; color:var(--muted); }}
.back-top {{ display:inline-flex; padding:9px 15px; border-radius:10px; background:var(--accent); color:var(--accent-ink); font-weight:750; text-decoration:none; }}
@media (min-width:1200px) {{ .has-navigation main {{ width:min(1000px,calc(100% - 180px)); transform:translateX(-46px); }} }}
@media (max-width:1199px) {{ body {{ padding-bottom:calc(88px + env(safe-area-inset-bottom)); }} .reading-rail,.rail-tooltip {{ display:none; }} .mobile-progress {{ position:fixed; z-index:100; right:14px; bottom:calc(12px + env(safe-area-inset-bottom)); left:14px; display:grid; grid-template-columns:minmax(86px,auto) minmax(0,1fr) minmax(86px,auto); align-items:center; gap:10px; min-height:68px; padding:9px; border:1px solid rgba(213,220,230,.94); border-radius:18px; background:rgba(255,255,255,.95); box-shadow:0 16px 45px rgba(23,32,51,.18); backdrop-filter:blur(16px); opacity:0; transform:translateY(calc(100% + 28px)); pointer-events:none; transition:opacity .2s ease,transform .2s ease; }} .js-ready .mobile-progress.is-visible {{ opacity:1; transform:translateY(0); pointer-events:auto; }} .mobile-control {{ display:flex; align-items:center; justify-content:center; gap:6px; min-height:48px; padding:8px 10px; border-radius:12px; color:var(--ink); font-size:.78rem; font-weight:800; text-decoration:none; }} .mobile-control:hover,.mobile-control:focus-visible {{ background:#f0f3f7; outline:none; }} .mobile-control.is-disabled {{ color:#a6afbd; pointer-events:none; }} .mobile-summary {{ min-width:0; }} .mobile-copy {{ display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:.78rem; }} #mobile-progress-label {{ white-space:nowrap; }} #mobile-progress-percent {{ color:var(--accent); font-weight:900; }} #mobile-progress-title {{ display:block; overflow:hidden; margin-top:1px; color:var(--muted); font-size:.72rem; white-space:nowrap; text-overflow:ellipsis; }} .mobile-progressbar {{ height:4px; margin-top:5px; overflow:hidden; border-radius:99px; background:#e3e7ed; }} .mobile-progress-fill {{ display:block; height:100%; border-radius:inherit; background:var(--accent); transition:width .2s ease; }} }}
@media (max-width:600px) {{ body {{ padding-bottom:calc(82px + env(safe-area-inset-bottom)); }} main {{ width:min(100% - 20px,1040px); margin-top:10px; }} .guide-header {{ min-height:auto; padding:30px 22px 34px; border-radius:22px; }} .hero-top {{ align-items:flex-start; flex-direction:column; margin-bottom:25px; }} .brand-logo {{ max-width:135px; height:36px; }} h1 {{ font-size:clamp(2.1rem,12vw,3.25rem); }} .hero-metrics {{ align-items:stretch; width:100%; padding:12px 14px; }} .hero-metric {{ grid-template-columns:1fr; gap:0; }} .metric-divider {{ height:auto; margin:0 14px; }} .hero-actions {{ display:grid; grid-template-columns:1fr; width:100%; }} .start-button,.tutorial-index summary {{ width:100%; }} .tutorial-index nav {{ position:relative; top:8px; width:100%; max-height:360px; margin-bottom:8px; }} .tutorial-index ol {{ grid-template-columns:1fr; }} .step {{ padding:14px; border-radius:15px; scroll-margin-top:18px; }} .instruction {{ margin-left:0; }} .mobile-progress {{ right:8px; bottom:calc(7px + env(safe-area-inset-bottom)); left:8px; grid-template-columns:52px minmax(0,1fr) 52px; gap:6px; min-height:64px; padding:7px; border-radius:16px; }} .mobile-control {{ min-width:48px; padding:7px; font-size:1.05rem; }} .mobile-control span:not([aria-hidden="true"]) {{ position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }} #mobile-progress-title {{ display:none; }} }}
@media (max-height:560px) and (max-width:1199px) {{ .mobile-progress {{ min-height:56px; }} }}
@media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} .start-button,.reading-rail,.rail-line-fill,.rail-dot,.rail-tooltip,.mobile-progress,.mobile-progress-fill,.step {{ transition:none; }} }}
@media print {{ html {{ scroll-behavior:auto; }} body {{ padding:0; background:white; }} main,.has-navigation main {{ width:100%; margin:0; transform:none; }} .guide-header {{ min-height:auto; padding:24px 0; border:0; box-shadow:none; }} .guide-header::before,.guide-header::after,.hero-actions,.reading-rail,.rail-tooltip,.mobile-progress,.back-top {{ display:none!important; }} .step,.step.is-active,.completion {{ box-shadow:none; page-break-inside:avoid; border-color:#dfe3e9; }} }}
</style>
</head>
<body{body_class}>
{navigation_html}
<main id="inicio" tabindex="-1">
<header class="guide-header"><div class="hero-top">{brand_html}<span class="guide-kicker">Tutorial paso a paso</span></div><h1>{_e(title)}</h1>{description_html}{metrics_html}{hero_actions}</header>
{chr(10).join(cards)}
{completion_html}
</main>
{script_html}
</body>
</html>
"""


def export_html(path: str | Path, project: TutorialProject) -> Path:
    target = Path(path)
    if target.suffix.lower() not in {".html", ".htm"}:
        target = target.with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_html(project), encoding="utf-8", newline="\n")
    return target
