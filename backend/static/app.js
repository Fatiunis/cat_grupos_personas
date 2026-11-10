// Dashboard de perfiles de uso. Lee la API de app/main.py; sin dependencias salvo Chart.js.
const $ = (s, r = document) => r.querySelector(s);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const color = (perfil) => css(`--s${(perfil % 8) + 1}`);
const fmt = (x, d = 0) => (x == null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("es", { maximumFractionDigits: d, minimumFractionDigits: d }));
const pct = (x) => (x == null ? "—" : `${fmt(100 * x)}\u00a0%`);
// Las horas llegan continuas desde la medianoche del día (25.5 = 01:30); se muestran en reloj de 24 h
const hora = (h) => (h == null ? "—" : ((h = ((h % 24) + 24) % 24), `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60) % 60).padStart(2, "0")}`));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const estado = { participantes: [], orden: { col: "id", asc: true }, corrida: null, graficos: {} };

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, opciones);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

function aviso(msg) {
  const a = $("#aviso");
  a.textContent = msg || "";
  a.hidden = !msg;
}

// ---------- Gráficos ----------

function opcionesBase(extra = {}) {
  const tinta2 = css("--tinta-2"), rejilla = css("--rejilla"), muted = css("--muted");
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { display: false }, tooltip: { backgroundColor: css("--superficie"), titleColor: css("--tinta"), bodyColor: tinta2, borderColor: css("--eje"), borderWidth: 1 } },
    scales: {
      x: { grid: { display: false }, ticks: { color: muted, maxRotation: 0, autoSkipPadding: 16 }, border: { color: css("--eje") } },
      y: { grid: { color: rejilla }, ticks: { color: muted }, border: { display: false }, beginAtZero: true },
    },
    ...extra,
  };
}

function grafico(id, config) {
  estado.graficos[id]?.destroy();
  estado.graficos[id] = new Chart($(`#${id}`), config);
  return estado.graficos[id];
}

function linea(id, etiquetas, valores, { formato = (v) => fmt(v), max, enteros = false } = {}) {
  const op = opcionesBase();
  op.scales.y.ticks.callback = formato;
  // Conteos de personas: solo marcas enteras (sin 1, 1, 2, 2… al redondear)
  if (enteros) op.scales.y.ticks.precision = 0;
  if (max != null) op.scales.y.max = max;
  op.plugins.tooltip.callbacks = { label: (c) => formato(c.parsed.y) };
  grafico(id, {
    type: "line",
    data: { labels: etiquetas, datasets: [{ data: valores, borderColor: css("--s1"), backgroundColor: css("--s1") + "1f", fill: "origin", borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5, cubicInterpolationMode: "monotone", spanGaps: true }] },
    options: op,
  });
}

// "Análisis 7 (simulación con estudios)": número del análisis guardado y con qué datos se hizo
const etiquetaCorrida = (c) => `Análisis ${c.id} (${!c.simulacion ? "tus participantes" : c.calibracion === "estudios" ? "simulación con estudios" : "simulación base"})`;

// ---------- Resumen ----------

function tile(valor, etiqueta, sub = "") {
  return `<div class="tile"><div class="valor">${valor}</div><div class="etiqueta">${etiqueta}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
}

async function cargarResumen() {
  const r = await api("/api/resumen");
  $("#tiles-resumen").innerHTML = [
    tile(fmt(r.participantes), "Participantes", r.excluidos ? `${r.excluidos} excluidos del análisis` : ""),
    tile(fmt(r.activos), "Activos", `enviaron en los últimos ${r.dias_activo} días`),
    tile(fmt(r.dias), "Días recolectados", r.fecha_inicio ? `${r.fecha_inicio} a ${r.fecha_fin}` : ""),
    tile(fmt(r.con_dias_suficientes ?? 0), "Con 14 días o más", "listos para tener perfil"),
    tile(fmt(r.con_bfi), "Con BFI-2", "cuestionario cargado"),
  ].join("");
  const f = r.serie.map((s) => s.fecha.slice(5));
  linea("g-personas", f, r.serie.map((s) => s.personas), { enteros: true });
  linea("g-pantalla", f, r.serie.map((s) => s.pantalla_mediana), { formato: (v) => `${fmt(v)} min` });
  linea("g-respuesta", f, r.serie.map((s) => s.respuesta_diaria), { formato: pct, max: 1 });
  $("#actualizado").textContent = `Actualizado ${new Date().toLocaleTimeString("es")} · se refresca cada 30 s`;

  const mini = $("#perfiles-mini");
  // Sin corrida real todavía, se muestra la última demostración (marcada como tal)
  let id = r.corrida_actual?.id;
  if (!id) id = (await api("/api/corridas")).find((x) => x.estado === "lista" && x.simulacion)?.id;
  if (!id) {
    mini.innerHTML = `<h3>Perfiles</h3><p class="muted">Todavía no hay una corrida del análisis. Ve a <a href="#analisis">Análisis</a> para crear una.</p>`;
    return;
  }
  const c = await api(`/api/corridas/${id}`);
  const total = c.perfiles.reduce((a, p) => a + p.n, 0);
  const reales = new Map();
  (c.ubicados || []).forEach((u) => reales.set(u.perfil, (reales.get(u.perfil) || 0) + 1));
  mini.innerHTML = `<h3>${c.simulacion ? "Perfiles de la demostración" : "Perfiles actuales"}</h3>
    <p class="muted">${c.simulacion ? '<span class="estado sim">Simulación</span> ' : ""}Análisis ${c.id} · ${new Date(c.creada).toLocaleDateString("es")}</p>
    <ul class="mini-perfiles">${c.perfiles.map((p) => `<li style="--c:${color(p.perfil)}">
      <div><span class="punto"></span>${esc(p.nombre)}</div>
      <div class="barra-mini"><span style="width:${(100 * p.n) / total}%"></span></div>
      <div class="muted">${pct(p.n / total)}${c.simulacion && reales.get(p.perfil) ? ` · ${reales.get(p.perfil)} de tus participantes` : ""}</div></li>`).join("")}</ul>
    <a class="ver-mas" href="#perfiles">Ver perfiles →</a>`;
}

// ---------- Participantes ----------

async function cargarParticipantes() {
  estado.participantes = await api("/api/participantes");
  const perfiles = [...new Map(estado.participantes.filter((p) => p.perfil != null).map((p) => [p.perfil, p.perfil_nombre])).entries()].sort((a, b) => a[0] - b[0]);
  const sel = $("#filtro-perfil"), actual = sel.value;
  sel.innerHTML = `<option value="">Todos los perfiles</option><option value="sin">Sin perfil</option>` +
    perfiles.map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("");
  sel.value = actual;
  pintarParticipantes();
}

// Perfil de una persona: el más probable; si la confianza es baja, también el segundo; y la marca de atípico
function celdaPerfil(perfil, nombre, prob, perfil2, nombre2, atipico) {
  if (perfil == null) return "";
  let h = `<span class="punto" style="--c:${color(perfil)}"></span>${esc(nombre)}`;
  if (prob != null && prob < 0.6 && perfil2 != null) h += ` <span class="muted">o</span> <span class="punto" style="--c:${color(perfil2)}"></span>${esc(nombre2)}`;
  if (atipico) h += ` <span class="estado atipico" title="No se parece mucho a ningún perfil">Atípico</span>`;
  return h;
}

function activo(p) {
  return p.ultimo_envio && Date.now() - new Date(p.ultimo_envio) < 3 * 864e5;
}

function pintarParticipantes() {
  const q = $("#buscar").value.trim().toLowerCase(), fp = $("#filtro-perfil").value, fe = $("#filtro-estado").value;
  const { col, asc } = estado.orden;
  const filas = estado.participantes
    .filter((p) => !q || p.id.toLowerCase().includes(q))
    .filter((p) => !fp || (fp === "sin" ? p.perfil == null : String(p.perfil) === fp))
    .filter((p) => !fe || (fe === "excluido" ? p.excluido : fe === "activo" ? activo(p) && !p.excluido : !activo(p)))
    .sort((a, b) => {
      const x = a[col] ?? -Infinity, y = b[col] ?? -Infinity;
      return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
    });
  $("#tabla-participantes tbody").innerHTML = filas.slice(0, 500).map((p) => `<tr data-id="${esc(p.id)}">
    <td>${esc(p.id)}</td><td class="num">${p.dias}</td><td class="num">${pct(p.cobertura)}</td>
    <td>${p.ultimo_envio ? new Date(p.ultimo_envio).toLocaleString("es", { dateStyle: "short", timeStyle: "short" }) : "—"}</td>
    <td>${p.perfil != null ? celdaPerfil(p.perfil, p.perfil_nombre, p.prob, p.perfil2, p.perfil2_nombre, p.atipico) : `<span class="muted">${p.dias < 14 ? "faltan días" : "sin corrida"}</span>`}</td>
    <td class="num">${p.prob != null ? pct(p.prob) : "—"}</td><td class="num">${fmt(p.bfi2, 2)}</td>
    <td>${p.excluido ? '<span class="estado mal">Excluido</span>' : activo(p) ? '<span class="estado ok">Activo</span>' : '<span class="estado">Inactivo</span>'}</td></tr>`).join("");
  $("#conteo-participantes").textContent = `${filas.length} de ${estado.participantes.length} participantes` + (filas.length > 500 ? " (se muestran 500; usa la búsqueda)" : "");
}

async function abrirParticipante(id) {
  const p = await api(`/api/participantes/${encodeURIComponent(id)}`);
  const cats = ["social", "mensajeria", "juegos", "video", "productividad", "educacion", "finanzas", "compras", "otros"];
  const tot = p.dias.reduce((a, d) => a + (d.pantalla_min || 0), 0) || 1;
  const reparto = cats.map((c) => [c, p.dias.reduce((a, d) => a + (d[`${c}_min`] || 0), 0) / tot]).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const actual = estado.participantes.find((x) => x.id === id);
  $("#detalle-cuerpo").innerHTML = `
    <h2>${esc(p.id)}</h2>
    <p class="muted">${p.dias.length} días · ${actual?.perfil_nombre ? `perfil actual: <span class="punto" style="--c:${color(actual.perfil)}"></span>${esc(actual.perfil_nombre)} (${pct(actual.prob)} de confianza)` : "sin perfil todavía"}</p>
    <figure class="tarjeta"><figcaption>Minutos de pantalla por día</figcaption><div class="lienzo"><canvas id="g-det-pantalla"></canvas></div></figure>
    <figure class="tarjeta"><figcaption>Tiempo por categoría (total del periodo)</figcaption><div class="lienzo"><canvas id="g-det-cat"></canvas></div></figure>
    ${p.historial.length > 1 ? `<div class="tarjeta"><h3>Perfil en cada corrida</h3><table>${p.historial.map((h) => `<tr><td>Análisis ${h.corrida}</td><td>${esc(h.nombre)}</td><td class="num">${pct(h.prob)}</td></tr>`).join("")}</table></div>` : ""}
    <div class="tarjeta">
      <h3>Gestión</h3>
      <div class="fila">
        <label>BFI-2 responsabilidad <input id="det-bfi" type="number" min="1" max="5" step="0.01" value="${p.bfi2 ?? ""}" style="width:90px"></label>
        <label><input id="det-excluido" type="checkbox" ${p.excluido ? "checked" : ""}> Excluir del análisis</label>
      </div>
      <p><textarea id="det-notas" placeholder="Notas internas">${esc(p.notas)}</textarea></p>
      <div class="fila"><button id="det-guardar" class="primario">Guardar</button>
        <button id="det-borrar" class="peligro">Borrar todos sus datos (retiro)</button></div>
    </div>`;
  $("#detalle").showModal();
  linea("g-det-pantalla", p.dias.map((d) => d.fecha.slice(5)), p.dias.map((d) => d.pantalla_min), { formato: (v) => `${fmt(v)} min` });
  const op = opcionesBase({ indexAxis: "y" });
  op.scales.x.ticks.callback = pct;
  op.scales.x.grid = { color: css("--rejilla") };
  op.scales.y.grid = { display: false };
  op.plugins.tooltip.callbacks = { label: (c) => pct(c.parsed.x) };
  grafico("g-det-cat", { type: "bar", data: { labels: reparto.map(([c]) => c), datasets: [{ data: reparto.map(([, v]) => v), backgroundColor: css("--s1"), borderRadius: 4, maxBarThickness: 18 }] }, options: op });

  $("#det-guardar").onclick = async () => {
    const v = $("#det-bfi").value;
    await api(`/api/participantes/${encodeURIComponent(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ excluido: $("#det-excluido").checked, notas: $("#det-notas").value, bfi2: v === "" ? null : Number(v) }) });
    $("#detalle").close();
    cargarParticipantes();
  };
  $("#det-borrar").onclick = async () => {
    if (!confirm(`¿Borrar definitivamente todos los datos de ${id}? No se puede deshacer.`)) return;
    await api(`/api/participantes/${encodeURIComponent(id)}`, { method: "DELETE" });
    $("#detalle").close();
    cargarParticipantes();
  };
}

// ---------- Perfiles ----------

const ETIQUETAS_Z = {
  pantalla_min_med: "Pantalla", desbloqueos_med: "Desbloqueos", uso_nocturno_min_med: "Uso nocturno", pct_social_med: "% redes sociales",
  pct_juegos_med: "% juegos", pct_productividad_med: "% productividad", hora_primer_uso_sd: "Irregularidad de horario",
  veces_bateria_baja_med: "Batería baja", pasos_med: "Pasos", lugares_distintos_med: "Lugares distintos",
};

async function cargarCorridas() {
  const lista = (await api("/api/corridas")).filter((c) => c.estado === "lista");
  const sel = $("#sel-corrida");
  sel.innerHTML = lista.map((c) => `<option value="${c.id}">${etiquetaCorrida(c)} · ${c.k} grupos · ${new Date(c.creada).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}</option>`).join("");
  if (!lista.length) {
    $("#tarjetas-perfil").innerHTML = `<p class="muted">No hay corridas terminadas. Crea una en <a href="#analisis">Análisis</a>.</p>`;
    return;
  }
  if (estado.corrida && lista.some((c) => c.id === estado.corrida.id)) sel.value = estado.corrida.id;
  await cargarCorrida(Number(sel.value));
}

function celdaZ(v) {
  const t = Math.min(Math.abs(v) / 1.5, 1);
  const base = v >= 0 ? css("--div-pos") : css("--div-neg");
  const fondo = `color-mix(in oklab, ${base} ${Math.round(t * 85)}%, ${css("--div-mid")})`;
  const tinta = t > 0.55 ? "#fff" : css("--tinta");
  return `<td class="celda" style="background:${fondo};color:${tinta}" title="${fmt(v, 2)} desv. est.">${v > 0 ? "+" : ""}${fmt(v, 1)}</td>`;
}

// Frases para describir un perfil según las variables en que más se aleja del promedio (alto, bajo)
const FRASES = {
  pantalla_min_med: ["pasan mucho tiempo frente a la pantalla", "usan poco el teléfono"],
  desbloqueos_med: ["lo revisan muy seguido", "lo desbloquean pocas veces al día"],
  uso_nocturno_min_med: ["lo usan de madrugada", "casi no lo usan de madrugada"],
  pct_social_med: ["dedican buena parte del tiempo a redes sociales", "dedican poco tiempo a redes sociales"],
  pct_juegos_med: ["dedican mucho tiempo a juegos", "casi no juegan"],
  pct_productividad_med: ["usan más apps de trabajo y productividad", "usan poco apps de productividad"],
  hora_primer_uso_sd: ["tienen horarios que cambian mucho de un día a otro", "mantienen horarios regulares"],
  veces_bateria_baja_med: ["suelen dejar que la batería se agote", "cuidan la batería"],
  pasos_med: ["caminan bastante", "caminan poco"],
  lugares_distintos_med: ["pasan por muchos lugares distintos", "se mueven por pocos lugares"],
};

// Señales para la responsabilidad, solo las que respaldan estudios publicados (ver informe):
// [1 si lo alto favorece, -1 si lo alto juega en contra, frase a favor, frase en contra, fuentes]
const SENALES = {
  hora_primer_uso_med: [-1, "Empieza el día temprano", "Empieza el día tarde", "Stachl 2020; Buzoku 2025"],
  hora_primer_uso_sd: [-1, "Horarios regulares", "Horarios que cambian mucho", "Stachl 2020"],
  hora_inicio_sueno_sd: [-1, "Hora de dormir estable", "Hora de dormir cambiante", "Stachl 2020; Kroese 2014"],
  uso_nocturno_min_med: [-1, "Casi sin uso de madrugada", "Uso de madrugada", "Kroese 2014; Guerreiro 2024"],
  pct_productividad_med: [1, "Más apps de organización y trabajo", "Pocas apps de organización y trabajo", "Stachl 2020"],
  desbloqueos_med: [-1, "Revisa el teléfono pocas veces", "Revisa el teléfono muy seguido", "Marengo 2020"],
};

function senales(z, umbral = 0.5) {
  const favor = [], contra = [];
  Object.entries(z || {}).filter(([v, x]) => SENALES[v] && Math.abs(x) >= umbral)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .forEach(([v, x]) => {
      const aFavor = Math.sign(x) === SENALES[v][0];
      (aFavor ? favor : contra).push({ texto: SENALES[v][aFavor ? 1 : 2], fuente: SENALES[v][3] });
    });
  return { favor, contra };
}

function bloqueSenales(z, umbral) {
  const s = senales(z, umbral);
  if (!s.favor.length && !s.contra.length) return `<p class="muted senal-vacia">Sin señales marcadas para la responsabilidad.</p>`;
  return `<div class="senales">${s.favor.map((t) => `<span class="senal a-favor" title="${t.fuente}">+ ${t.texto}</span>`).join("")}${s.contra.map((t) => `<span class="senal en-contra" title="${t.fuente}">− ${t.texto}</span>`).join("")}</div>`;
}

function definicion(p, bfiPerfil, bfiGeneral) {
  const rasgos = Object.entries(p.z || {})
    .filter(([v, z]) => FRASES[v] && Math.abs(z) >= 0.5)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3)
    .map(([v, z]) => (Math.abs(z) >= 1.2 ? "<b>" : "") + FRASES[v][z > 0 ? 0 : 1] + (Math.abs(z) >= 1.2 ? "</b>" : ""));
  const lista = rasgos.length > 1 ? `${rasgos.slice(0, -1).join(", ")} y ${rasgos.at(-1)}` : rasgos[0];
  let t = lista ? `Personas que ${lista}.` : "Personas con un uso cercano al promedio en casi todo.";
  if (bfiPerfil && bfiGeneral != null) {
    const d = bfiPerfil.media - bfiGeneral;
    t += ` Responsabilidad (BFI-2) ${fmt(bfiPerfil.media, 2)}, ${Math.abs(d) < 0.1 ? "parecida al" : d > 0 ? "por encima del" : "por debajo del"} promedio (${fmt(bfiGeneral, 2)}).`;
  }
  return t;
}

async function cargarCorrida(id) {
  const c = await api(`/api/corridas/${id}`);
  estado.corrida = c;
  $("#aviso-sim").hidden = !c.simulacion;
  const m = c.metricas;
  $("#tiles-perfiles").innerHTML = [
    tile(fmt(m.personas), "Personas con perfil", `${m.sin_perfil_pocos_dias} sin perfil por pocos días`),
    tile(c.k, "Perfiles", c.k_pedido ? "fijado a mano" : `elegido automáticamente`),
    tile(pct(m.baja_confianza), "Asignación dudosa", "confianza menor a 60 %; se muestra la 2.ª opción"),
    m.atipicos != null ? tile(fmt(m.atipicos), "Atípicos", "no se parecen mucho a ningún perfil") : "",
    m.exactitud_clasificador != null ? tile(pct(m.exactitud_clasificador), "Exactitud del clasificador", "para asignar personas nuevas") : "",
    m.r_responsabilidad != null ? tile(fmt(m.r_responsabilidad, 2), "Correlación con BFI-2", "predicción vs. cuestionario (r)") : "",
    m.ari_arquetipos != null ? tile(fmt(m.ari_arquetipos, 2), "ARI vs. arquetipos", "solo sintéticos, meta ≥ 0,7") : "",
  ].join("");

  const bfi = new Map((c.responsabilidad || []).map((r) => [r.perfil, r]));
  const nBfi = (c.responsabilidad || []).reduce((a, r) => a + r.n, 0);
  const bfiGeneral = nBfi ? c.responsabilidad.reduce((a, r) => a + r.media * r.n, 0) / nBfi : null;
  $("#tarjetas-perfil").innerHTML = c.perfiles.map((p) => {
    const md = p.medianas;
    return `<div class="tarjeta perfil" style="--c:${color(p.perfil)}">
      <textarea class="nombre" rows="2" data-perfil="${p.perfil}" aria-label="Nombre del perfil" title="Clic para renombrar">${esc(p.nombre)}</textarea>
      <div class="muted">${p.n} personas · confianza media ${pct(p.prob_media)}</div>
      <p class="definicion">${definicion(p, bfi.get(p.perfil), bfiGeneral)}</p>
      ${bloqueSenales(p.z)}
      <dl>
        <dt>Pantalla al día</dt><dd>${fmt((md.pantalla_min ?? 0) / 60, 1)} h</dd>
        <dt>Desbloqueos</dt><dd>${fmt(md.desbloqueos)}</dd>
        <dt>Uso nocturno (0–5 h)</dt><dd>${fmt(md.uso_nocturno_min)} min</dd>
        <dt>Primer / último uso</dt><dd>${hora(md.hora_primer_uso)} / ${hora(md.hora_ultimo_uso)}</dd>
        <dt>Redes / juegos</dt><dd>${pct(md.pct_social)} / ${pct(md.pct_juegos)}</dd>
        ${md.q_cumplimiento != null ? `<dt>Cumplimiento diario (1–5)</dt><dd>${fmt(md.q_cumplimiento, 1)}</dd>` : ""}
        ${bfi.has(p.perfil) ? `<dt>BFI-2 responsabilidad</dt><dd>${fmt(bfi.get(p.perfil).media, 2)}</dd>` : ""}
      </dl></div>`;
  }).join("");
  document.querySelectorAll(".perfil .nombre").forEach((inp) => {
    inp.onchange = async () => {
      await api(`/api/corridas/${c.id}/perfiles/${inp.dataset.perfil}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nombre: inp.value }) });
      c.perfiles.find((p) => String(p.perfil) === inp.dataset.perfil).nombre = inp.value;
      pintarMapa();
      pintarBfi();
      pintarTablaZ();
    };
  });

  const sel = $("#resaltar");
  sel.innerHTML = `<option value="">Todos los perfiles</option>` + c.perfiles.map((p) => `<option value="${p.perfil}">${esc(p.nombre)}</option>`).join("");
  sel.onchange = pintarMapa;
  $("#nota-mapa").textContent = `Las dos componentes explican ${pct(m.varianza_mapa)} de la variación; perfiles que se solapan aquí pueden separarse en otras dimensiones.`;
  pintarMapa();
  pintarBfi();
  pintarTablaZ();

  const ub = c.ubicados || [];
  $("#bloque-ubicados").hidden = !c.simulacion;
  const nombreP = (k) => c.perfiles.find((p) => p.perfil === k)?.nombre ?? k;
  $("#tabla-ubicados").innerHTML = ub.length
    ? `<tr><th>Participante</th><th class="num">Días</th><th>Perfil más parecido</th><th class="num">Confianza</th></tr>` +
      ub.sort((a, b) => b.dias - a.dias).map((u) => `<tr class="clicable" data-id="${esc(u.id)}"><td>${esc(u.id.slice(0, 8))}</td><td class="num">${u.dias}</td>` +
        `<td>${celdaPerfil(u.perfil, nombreP(u.perfil), u.prob, u.perfil2, nombreP(u.perfil2), u.atipico)}</td><td class="num">${pct(u.prob)}</td></tr>`).join("")
    : `<tr><td class="muted">Aún no hay días de participantes reales para ubicar.</td></tr>`;
  document.querySelectorAll("#tabla-ubicados tr[data-id]").forEach((tr) => (tr.onclick = () => abrirParticipante(tr.dataset.id)));

  const cr = c.cruce_arquetipos;
  $("#bloque-cruce").hidden = !cr;
  if (cr) {
    const nombre = (k) => c.perfiles.find((p) => p.perfil === k)?.nombre ?? k;
    $("#tabla-cruce").innerHTML = `<tr><th>Arquetipo</th>${cr.columnas.map((k) => `<th class="num"><span class="punto" style="--c:${color(k)}"></span>${esc(nombre(k))}</th>`).join("")}</tr>` +
      cr.filas.map((f, i) => `<tr><td>${esc(f)}</td>${cr.valores[i].map((v) => `<td class="num">${v || ""}</td>`).join("")}</tr>`).join("");
  }
  $("#link-perfiles").href = `/api/exportar/perfiles.csv?corrida=${c.id}`;
}

function pintarMapa() {
  const c = estado.corrida, foco = $("#resaltar").value, gris = css("--eje");
  // Con más de 3 colores en un mismo plano no se distinguen bien: se resalta un perfil a la vez
  const datasets = c.perfiles.map((p) => {
    const activo = foco === "" || String(p.perfil) === foco;
    return {
      label: p.nombre, perfil: p.perfil,
      data: c.puntos.filter((x) => x.perfil === p.perfil),
      backgroundColor: activo ? color(p.perfil) : gris, borderColor: css("--superficie"), borderWidth: 1,
      pointRadius: activo && foco !== "" ? 5 : 4, pointHoverRadius: 7, order: activo ? 0 : 1,
    };
  });
  if (c.ubicados?.length) {
    datasets.push({
      label: "Tus participantes", data: c.ubicados, pointStyle: "rectRot", pointRadius: 8, pointHoverRadius: 10,
      backgroundColor: c.ubicados.map((u) => color(u.perfil)), borderColor: css("--tinta"), borderWidth: 2, order: -1,
    });
  }
  const op = opcionesBase({ interaction: { mode: "nearest", intersect: true } });
  op.scales.y.beginAtZero = false;
  op.scales.x.grid = { color: css("--rejilla") };
  op.plugins.legend = { display: true, position: "bottom", labels: { color: css("--tinta-2"), usePointStyle: true, boxWidth: 8 } };
  const nombreP = (k) => c.perfiles.find((p) => p.perfil === k)?.nombre ?? k;
  op.plugins.tooltip.callbacks = { label: (ctx) => ctx.raw.dias != null
    ? `${ctx.raw.id.slice(0, 8)} (real, ${ctx.raw.dias} días) · ${nombreP(ctx.raw.perfil)} (${pct(ctx.raw.prob)})`
    : `${ctx.raw.id} · ${ctx.dataset.label} (${pct(ctx.raw.prob)})` };
  op.onClick = (_, els) => {
    const x = els.length && datasets[els[0].datasetIndex].data[els[0].index];
    // En una simulación solo los puntos reales tienen ficha
    if (x && (!c.simulacion || x.dias != null)) abrirParticipante(x.id);
  };
  grafico("g-mapa", { type: "scatter", data: { datasets }, options: op });
}

function pintarBfi() {
  const c = estado.corrida, r = c.responsabilidad;
  $("#nota-bfi").textContent = r ? "Pasa el cursor para ver la desviación estándar y el número de personas." : "Carga los resultados del BFI-2 en Análisis para ver esta comparación.";
  const nombre = (k) => c.perfiles.find((p) => p.perfil === k)?.nombre ?? k;
  const op = opcionesBase({ indexAxis: "y", interaction: { mode: "nearest", intersect: false } });
  op.scales.x = { ...op.scales.x, min: 1, max: 5, grid: { color: css("--rejilla") } };
  op.scales.y = { ...op.scales.y, beginAtZero: false, grid: { display: false }, ticks: { color: css("--tinta-2"), autoSkip: false } };
  op.plugins.tooltip.callbacks = { label: (ctx) => { const x = r[ctx.dataIndex]; return `media ${fmt(x.media, 2)} · desv. ${fmt(x.sd, 2)} · ${x.n} personas`; } };
  grafico("g-bfi", {
    type: "bar",
    data: { labels: (r || []).map((x) => nombre(x.perfil)), datasets: [{ data: (r || []).map((x) => x.media), backgroundColor: (r || []).map((x) => color(x.perfil)), borderRadius: 4, maxBarThickness: 22 }] },
    options: op,
  });
}

function pintarTablaZ() {
  const c = estado.corrida, vars = Object.keys(c.perfiles[0]?.z || {});
  $("#tabla-z").innerHTML = `<tr><th>Perfil</th>${vars.map((v) => `<th>${ETIQUETAS_Z[v] || v}</th>`).join("")}</tr>` +
    c.perfiles.map((p) => `<tr><td><span class="punto" style="--c:${color(p.perfil)}"></span>${esc(p.nombre)}</td>${vars.map((v) => celdaZ(p.z[v] ?? 0)).join("")}</tr>`).join("");
}

// ---------- Análisis ----------

let sondeo = null;

async function cargarAnalisis() {
  const lista = await api("/api/corridas");
  $("#tabla-corridas").innerHTML = lista.length
    ? `<tr><th>Corrida</th><th>Fecha</th><th>Estado</th><th class="num">Personas</th><th class="num">Perfiles</th><th></th></tr>` +
      lista.map((c) => `<tr><td>${c.id}${c.simulacion ? ' <span class="estado sim">Simulación</span>' : ""}</td><td>${new Date(c.creada).toLocaleString("es")}</td>
        <td>${c.estado === "lista" ? '<span class="estado ok">Lista</span>' : c.estado === "error" ? `<span class="estado mal" title="${esc(c.error)}">Error</span> <span class="muted">${esc(c.error)}</span>` : '<span class="estado">Corriendo…</span>'}</td>
        <td class="num">${fmt(c.personas)}</td><td class="num">${c.k ?? "—"}${c.k_pedido ? " (fijo)" : ""}</td>
        <td><button data-borrar="${c.id}" class="peligro">Borrar</button></td></tr>`).join("")
    : `<tr><td class="muted">Todavía no hay corridas.</td></tr>`;
  document.querySelectorAll("[data-borrar]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm(`¿Borrar la corrida ${b.dataset.borrar}?`)) return;
      await api(`/api/corridas/${b.dataset.borrar}`, { method: "DELETE" });
      cargarAnalisis();
    };
  });
  clearTimeout(sondeo);
  if (lista.some((c) => c.estado === "corriendo")) sondeo = setTimeout(cargarAnalisis, 3000);

  const ultima = lista.find((c) => c.estado === "lista");
  $("#graficos-k").hidden = !ultima;
  if (ultima) {
    const c = await api(`/api/corridas/${ultima.id}`);
    const ks = c.tabla_k.map((t) => String(t.k));
    linea("g-bic", ks, c.tabla_k.map((t) => t.bic), { formato: (v) => fmt(v) });
    estado.graficos["g-bic"].options.scales.y.beginAtZero = false;
    estado.graficos["g-bic"].data.datasets[0].pointRadius = 4;
    estado.graficos["g-bic"].update();
    linea("g-estab", ks, c.tabla_k.map((t) => t.estabilidad), { formato: (v) => fmt(v, 2), max: 1 });
    estado.graficos["g-estab"].data.datasets[0].pointRadius = 4;
    estado.graficos["g-estab"].update();
  }
}

$("#form-corrida").onsubmit = async (e) => {
  e.preventDefault();
  const k = new FormData(e.target).get("k");
  try {
    await api("/api/corridas", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ k: k ? Number(k) : null }) });
    cargarAnalisis();
  } catch (err) { aviso(err.message); }
};

async function correrSimulacion(calibracion) {
  await api("/api/corridas", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ simulacion: true, calibracion }) });
}
document.querySelectorAll("[data-simulacion]").forEach((b) => (b.onclick = async () => {
  try {
    await correrSimulacion(b.dataset.simulacion);
    if (location.hash === "#modelo") cargarModelo(); else cargarAnalisis();
  } catch (err) { aviso(err.message); }
}));

$("#form-etiquetas").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const r = await api("/api/etiquetas", { method: "POST", body: new FormData(e.target) });
    $("#res-etiquetas").textContent = `${r.actualizados} participantes actualizados` + (r.n_desconocidos ? `; ${r.n_desconocidos} IDs no encontrados (${r.desconocidos.slice(0, 5).join(", ")})` : "");
  } catch (err) { $("#res-etiquetas").textContent = err.message; }
};

// ---------- Responsabilidad ----------

const NIVEL_INFO = {
  baja: { nombre: "Baja", color: "--s5" },
  media_baja: { nombre: "Media baja", color: "--s2" },
  media_alta: { nombre: "Media alta", color: "--s7" },
  alta: { nombre: "Alta", color: "--s1" },
};
const rangoNivel = (g) => `BFI-2 de ${fmt(g.rango[0], 1)} a ${fmt(g.rango[1], 1)}`;

async function cargarResponsabilidad() {
  const lista = (await api("/api/corridas")).filter((c) => c.estado === "lista");
  const sel = $("#sel-corrida-r");
  const actual = Number(sel.value) || (lista.find((c) => !c.simulacion) || lista[0])?.id;
  sel.innerHTML = lista.map((c) => `<option value="${c.id}">${etiquetaCorrida(c)} · ${new Date(c.creada).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}</option>`).join("");
  if (!actual) {
    $("#resp-cuerpo").innerHTML = `<div class="tarjeta"><p class="muted">Todavía no hay corridas. Ve a <a href="#analisis">Análisis</a> y corre la demostración o el análisis.</p></div>`;
    return;
  }
  sel.value = actual;
  const c = await api(`/api/corridas/${actual}`);
  $("#aviso-sim-r").hidden = !c.simulacion;
  const n = c.niveles;
  if (!n || !n.grupos) {
    $("#resp-cuerpo").innerHTML = `<div class="tarjeta"><h3>Faltan cuestionarios</h3><p class="muted">Los niveles se forman con el BFI-2. Esta corrida tiene ${n?.con_bfi ?? 0} personas con cuestionario y se necesitan 30 (faltan ${n?.faltan ?? 30}). Mientras tanto puedes ver cómo se vería con la demostración.</p></div>`;
    return;
  }
  const nombreP = (k) => c.perfiles.find((p) => p.perfil === Number(k))?.nombre ?? `Perfil ${k}`;
  const m = c.metricas;
  const tiles = [
    tile(fmt(n.con_bfi), "Personas con BFI-2", c.simulacion ? "sintéticas" : "con 14 días o más"),
    ...n.grupos.map((g) => tile(fmt(g.n), `Responsabilidad ${NIVEL_INFO[g.nivel].nombre.toLowerCase()}`, `${pct(g.n / n.con_bfi)} · media ${fmt(g.media_bfi, 2)}`)),
    m.r_responsabilidad != null ? tile(fmt(m.r_responsabilidad, 2), "Qué tanto lo predice el uso", `correlación; error típico ±${fmt(n.rmse, 1)} puntos`) : "",
  ].join("");
  const tarjetas = n.grupos.map((g) => {
    const info = NIVEL_INFO[g.nivel], md = g.medianas || {};
    const total = Object.values(g.perfiles).reduce((a, b) => a + b, 0);
    const mezcla = Object.entries(g.perfiles).sort((a, b) => b[1] - a[1]).map(([p, k]) => `<li style="--c:${color(Number(p))}">
      <div><span class="punto"></span>${esc(nombreP(p))} <span class="muted">${pct(k / total)}</span></div>
      <div class="barra-mini"><span style="width:${(100 * k) / total}%"></span></div></li>`).join("");
    return `<div class="tarjeta nivel" style="--c:var(${info.color})">
      <div class="nivel-cabeza"><h3>Responsabilidad ${info.nombre.toLowerCase()}</h3><span class="muted">${rangoNivel(g)} · ${g.n} personas</span></div>
      ${bloqueSenales(g.z, 0.3)}
      <dl>
        <dt>Pantalla al día</dt><dd>${fmt((md.pantalla_min ?? 0) / 60, 1)} h</dd>
        <dt>Desbloqueos</dt><dd>${fmt(md.desbloqueos)}</dd>
        <dt>Uso nocturno (0–5 h)</dt><dd>${fmt(md.uso_nocturno_min)} min</dd>
        <dt>Primer / último uso</dt><dd>${hora(md.hora_primer_uso)} / ${hora(md.hora_ultimo_uso)}</dd>
        ${md.q_cumplimiento != null ? `<dt>Cumplimiento diario (1–5)</dt><dd>${fmt(md.q_cumplimiento, 1)}</dd>` : ""}
      </dl>
      <h4>Perfiles de uso en este nivel</h4><ul class="mini-perfiles">${mezcla}</ul></div>`;
  }).join("");
  const est = n.estimados || [];
  const tablaEst = `<div class="tarjeta"><h3>${c.simulacion ? "Tus participantes: nivel estimado por su uso" : "Participantes sin BFI-2: nivel estimado por su uso"}</h3>
    <p class="muted">Estimación a partir del uso del teléfono, con un error típico de ±${fmt(n.rmse, 1)} puntos. No reemplaza el cuestionario.</p>
    ${est.length ? `<div class="tabla-envoltorio"><table><tr><th>Participante</th><th class="num">BFI-2 estimado</th><th>Nivel estimado</th></tr>${est.sort((a, b) => b.valor - a.valor).map((e) => `<tr class="clicable" data-id="${esc(e.id)}"><td>${esc(e.id.slice(0, 8))}</td><td class="num">${fmt(e.valor, 1)}</td><td><span class="punto" style="--c:var(${NIVEL_INFO[e.nivel].color})"></span>${NIVEL_INFO[e.nivel].nombre}</td></tr>`).join("")}</table></div>` : `<p class="muted">No hay personas para estimar.</p>`}</div>`;
  $("#resp-cuerpo").innerHTML = `<div class="tiles">${tiles}</div><div class="niveles">${tarjetas}</div>${tablaEst}
    <p class="muted">Los cuatro niveles son los cuartiles del grupo: cada uno junta a un cuarto de las personas con BFI-2 (cortes en ${n.cortes.map((x) => fmt(x, 2)).join(", ")}). Las señales a favor y en contra vienen de estudios publicados (pasa el cursor sobre cada una para ver la fuente); describen tendencias del grupo, no juicios sobre cada persona.</p>`;
  document.querySelectorAll("#resp-cuerpo tr[data-id]").forEach((tr) => (tr.onclick = () => abrirParticipante(tr.dataset.id).catch(() => {})));
}

// ---------- Modelo ----------

const ETAPAS = {
  base: { titulo: "1 · Simulación base", datos: "300 personas sintéticas con seis arquetipos bien separados",
    cambio: "Primer ensayo: arquetipos marcados y una relación con la responsabilidad que depende del arquetipo. Sirve para comprobar que el método recupera grupos cuando existen." },
  estudios: { titulo: "2 · Simulación calibrada con estudios", datos: "300 personas sintéticas ajustadas a cifras publicadas",
    cambio: "Uso diario de unas 4 h y unos 80 desbloqueos (Andrews 2015, Bentley 2015, dscout 2016), arquetipos más mezclados entre sí, más de la mitad de usos cortos y una responsabilidad propia de cada persona que adelanta horarios y reduce el uso de madrugada con un efecto pequeño (Stachl 2020: r de 0,31)." },
  reales: { titulo: "3 · Datos reales", datos: "Participantes reales con 14 días o más",
    cambio: "El análisis con las personas que mandaron datos. Hoy son muy pocas para formar perfiles propios, por eso se ubican en el modelo calibrado." },
};

async function cargarModelo() {
  const m = await api("/api/modelo");
  const filas = m.etapas.map((e) => {
    const info = ETAPAS[e.tipo];
    if (!e.id) return `<tr><td><b>${info.titulo}</b><div class="muted">${info.datos}</div></td><td colspan="6" class="muted">Sin corrida todavía${e.tipo !== "reales" ? ` · <button type="button" class="enlace" data-sim-modelo="${e.tipo}">Correrla ahora</button>` : ""}</td></tr>`;
    const x = e.metricas;
    return `<tr><td><b>${info.titulo}</b><div class="muted">${info.datos} · corrida ${e.id}</div></td>
      <td class="num">${fmt(x.personas)}</td><td class="num">${fmt(e.k)}</td>
      <td class="num">${x.ari_arquetipos != null ? fmt(x.ari_arquetipos, 2) : "—"}</td>
      <td class="num">${x.r_responsabilidad != null ? fmt(x.r_responsabilidad, 2) : "—"}</td>
      <td class="num">${x.baja_confianza != null ? pct(x.baja_confianza) : "—"}</td>
      <td class="num">${fmt(x.atipicos)}</td></tr>`;
  }).join("");
  const cambios = m.etapas.map((e) => `<li><b>${ETAPAS[e.tipo].titulo}.</b> ${ETAPAS[e.tipo].cambio}</li>`).join("");
  const fin = m.etapas.find((e) => e.tipo === m.final);
  let final = `<div class="tarjeta"><h3>Modelo final</h3><p class="muted">Corre la simulación calibrada con estudios para ver el modelo final.</p></div>`;
  if (fin && fin.id) {
    const total = fin.perfiles.reduce((a, p) => a + p.n, 0);
    const perfiles = fin.perfiles.sort((a, b) => b.n - a.n).map((p) => `<li style="--c:${color(p.perfil)}">
      <div><span class="punto"></span>${esc(p.nombre)} <span class="muted">${pct(p.n / total)}</span></div>
      <div class="barra-mini"><span style="width:${(100 * p.n) / total}%"></span></div></li>`).join("");
    const ub = fin.ubicados.length ? `<table><tr><th>Participante</th><th class="num">Días</th><th>Perfil</th><th class="num">Confianza</th></tr>${fin.ubicados.map((u) => `<tr class="clicable" data-id="${esc(u.id)}"><td>${esc(u.id.slice(0, 8))}</td><td class="num">${fmt(u.dias)}</td>
      <td><span class="punto" style="--c:${color(u.perfil)}"></span>${esc(u.nombre)}${u.atipico ? ' <span class="estado atipico">Atípico</span>' : ""}</td><td class="num">${pct(u.prob)}</td></tr>`).join("")}</table>` : `<p class="muted">Aún no hay participantes reales para ubicar.</p>`;
    final = `<div class="grid2"><div class="tarjeta"><h3>Modelo final: ${fmt(fin.k)} perfiles</h3>
      <p class="muted">Simulación calibrada con estudios (corrida ${fin.id}). Es el modelo que se usa para ubicar a los participantes reales mientras no haya suficientes para formar perfiles propios.</p>
      <ul class="mini-perfiles">${perfiles}</ul></div>
      <div class="tarjeta"><h3>Dónde quedan tus participantes</h3><p class="muted">La marca de atípico solo se da con 14 días o más.</p><div class="tabla-envoltorio tabla-ubicados">${ub}</div></div></div>`;
  }
  $("#modelo-cuerpo").innerHTML = `<div class="tarjeta"><h3>Cómo cambió el modelo</h3>
    <div class="tabla-envoltorio"><table class="tabla-etapas"><tr><th>Etapa</th><th class="num">Personas</th><th class="num">Perfiles</th><th class="num" title="Qué tanto coinciden los perfiles con los arquetipos plantados (0 a 1)">Coincide con arquetipos</th><th class="num" title="Correlación entre la responsabilidad estimada por el uso y la del BFI-2">Predice responsab.</th><th class="num">Dudosas</th><th class="num">Atípicos</th></tr>${filas}</table></div>
    <p class="muted">La coincidencia con arquetipos solo existe en simulaciones. En estudios con datos reales la responsabilidad se predice con r cerca de 0,3 (Stachl 2020); una cifra mucho más alta en la simulación indica que está demasiado ordenada.</p></div>
    <div class="tarjeta"><h3>Qué cambió en cada etapa</h3><ul class="lista-cambios">${cambios}</ul></div>${final}`;
  document.querySelectorAll("#modelo-cuerpo [data-sim-modelo]").forEach((b) => (b.onclick = () => correrSimulacion(b.dataset.simModelo).then(() => aviso("Corriendo… vuelve a abrir esta pestaña en un minuto.")).catch((e) => aviso(e.message))));
  document.querySelectorAll("#modelo-cuerpo tr[data-id]").forEach((tr) => (tr.onclick = () => abrirParticipante(tr.dataset.id).catch(() => {})));
}

// ---------- Navegación ----------

const cargadores = { resumen: cargarResumen, participantes: cargarParticipantes, perfiles: cargarCorridas, responsabilidad: cargarResponsabilidad, modelo: cargarModelo, analisis: cargarAnalisis };
let refresco = null;

async function mostrar(vista) {
  if (!cargadores[vista]) vista = "resumen";
  document.querySelectorAll("#pestanas button").forEach((b) => b.setAttribute("aria-selected", b.dataset.vista === vista));
  document.querySelectorAll(".vista").forEach((s) => (s.hidden = s.id !== `vista-${vista}`));
  clearInterval(refresco);
  if (vista === "resumen") refresco = setInterval(() => cargarResumen().catch((e) => aviso(e.message)), 30000);
  try {
    aviso("");
    await cargadores[vista]();
  } catch (e) { aviso(`No se pudieron cargar los datos: ${e.message}`); }
}

document.querySelectorAll("#pestanas button").forEach((b) => (b.onclick = () => (location.hash = b.dataset.vista)));
window.addEventListener("hashchange", () => mostrar(location.hash.slice(1)));
$("#buscar").oninput = pintarParticipantes;
$("#filtro-perfil").onchange = pintarParticipantes;
$("#filtro-estado").onchange = pintarParticipantes;
$("#sel-corrida").onchange = (e) => cargarCorrida(Number(e.target.value));
$("#sel-corrida-r").onchange = () => cargarResponsabilidad().catch((e) => aviso(e.message));
$("#tabla-participantes thead").onclick = (e) => {
  const col = e.target.dataset.col;
  if (!col) return;
  estado.orden = { col, asc: estado.orden.col === col ? !estado.orden.asc : true };
  pintarParticipantes();
};
$("#tabla-participantes tbody").onclick = (e) => {
  const tr = e.target.closest("tr");
  if (tr) abrirParticipante(tr.dataset.id);
};
Chart.defaults.font.family = '"Nunito", system-ui, -apple-system, "Segoe UI", sans-serif';
mostrar(location.hash.slice(1));
