// Dashboard de perfiles de uso. Lee la API de app/main.py; sin dependencias salvo Chart.js.
const $ = (s, r = document) => r.querySelector(s);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const color = (perfil) => css(`--s${(perfil % 8) + 1}`);
const fmt = (x, d = 0) => (x == null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("es", { maximumFractionDigits: d, minimumFractionDigits: d }));
const pct = (x) => (x == null ? "—" : `${fmt(100 * x)}\u00a0%`);
const hora = (h) => (h == null ? "—" : `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60) % 60).padStart(2, "0")}`);
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

function linea(id, etiquetas, valores, { formato = (v) => fmt(v), max } = {}) {
  const op = opcionesBase();
  op.scales.y.ticks.callback = formato;
  if (max != null) op.scales.y.max = max;
  op.plugins.tooltip.callbacks = { label: (c) => formato(c.parsed.y) };
  grafico(id, {
    type: "line",
    data: { labels: etiquetas, datasets: [{ data: valores, borderColor: css("--s1"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.2, spanGaps: true }] },
    options: op,
  });
}

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
  linea("g-personas", f, r.serie.map((s) => s.personas));
  linea("g-pantalla", f, r.serie.map((s) => s.pantalla_mediana), { formato: (v) => `${fmt(v)} min` });
  linea("g-respuesta", f, r.serie.map((s) => s.respuesta_diaria), { formato: pct, max: 1 });
  $("#actualizado").textContent = `Actualizado ${new Date().toLocaleTimeString("es")} · se refresca cada 30 s`;

  const mini = $("#perfiles-mini");
  if (!r.corrida_actual) {
    mini.innerHTML = `<h3>Perfiles</h3><p class="muted">Todavía no hay una corrida del análisis. Ve a <a href="#analisis">Análisis</a> para crear una.</p>`;
    return;
  }
  const c = await api(`/api/corridas/${r.corrida_actual.id}`);
  const total = c.perfiles.reduce((a, p) => a + p.n, 0);
  mini.innerHTML = `<h3>Perfiles actuales</h3><p class="muted">Corrida ${c.id}, ${new Date(c.creada).toLocaleString("es")}</p>
    <table>${c.perfiles.map((p) => `<tr><td><span class="punto" style="--c:${color(p.perfil)}"></span>${esc(p.nombre)}</td>
      <td class="num">${p.n}</td><td class="num">${pct(p.n / total)}</td></tr>`).join("")}</table>`;
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
    <td>${p.perfil != null ? `<span class="punto" style="--c:${color(p.perfil)}"></span>${esc(p.perfil_nombre)}` : `<span class="muted">${p.dias < 14 ? "faltan días" : "sin corrida"}</span>`}</td>
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
    ${p.historial.length > 1 ? `<div class="tarjeta"><h3>Perfil en cada corrida</h3><table>${p.historial.map((h) => `<tr><td>Corrida ${h.corrida}</td><td>${esc(h.nombre)}</td><td class="num">${pct(h.prob)}</td></tr>`).join("")}</table></div>` : ""}
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
  sel.innerHTML = lista.map((c) => `<option value="${c.id}">Corrida ${c.id} · ${c.k} perfiles · ${new Date(c.creada).toLocaleString("es", { dateStyle: "short", timeStyle: "short" })}</option>`).join("");
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

async function cargarCorrida(id) {
  const c = await api(`/api/corridas/${id}`);
  estado.corrida = c;
  const m = c.metricas;
  $("#tiles-perfiles").innerHTML = [
    tile(fmt(m.personas), "Personas con perfil", `${m.sin_perfil_pocos_dias} sin perfil por pocos días`),
    tile(c.k, "Perfiles", c.k_pedido ? "fijado a mano" : `elegido automáticamente`),
    tile(pct(m.baja_confianza), "Asignación dudosa", "confianza menor a 60 %"),
    m.exactitud_clasificador != null ? tile(pct(m.exactitud_clasificador), "Exactitud del clasificador", "para asignar personas nuevas") : "",
    m.r_responsabilidad != null ? tile(fmt(m.r_responsabilidad, 2), "Correlación con BFI-2", "predicción vs. cuestionario (r)") : "",
    m.ari_arquetipos != null ? tile(fmt(m.ari_arquetipos, 2), "ARI vs. arquetipos", "solo sintéticos, meta ≥ 0,7") : "",
  ].join("");

  const bfi = new Map((c.responsabilidad || []).map((r) => [r.perfil, r]));
  $("#tarjetas-perfil").innerHTML = c.perfiles.map((p) => {
    const md = p.medianas;
    return `<div class="tarjeta perfil" style="--c:${color(p.perfil)}">
      <textarea class="nombre" rows="2" data-perfil="${p.perfil}" aria-label="Nombre del perfil" title="Clic para renombrar">${esc(p.nombre)}</textarea>
      <div class="muted">${p.n} personas · confianza media ${pct(p.prob_media)}</div>
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
  const op = opcionesBase({ interaction: { mode: "nearest", intersect: true } });
  op.scales.y.beginAtZero = false;
  op.scales.x.grid = { color: css("--rejilla") };
  op.plugins.legend = { display: true, position: "bottom", labels: { color: css("--tinta-2"), usePointStyle: true, boxWidth: 8 } };
  op.plugins.tooltip.callbacks = { label: (ctx) => `${ctx.raw.id} · ${ctx.dataset.label} (${pct(ctx.raw.prob)})` };
  op.onClick = (_, els) => { if (els.length) abrirParticipante(datasets[els[0].datasetIndex].data[els[0].index].id); };
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
      lista.map((c) => `<tr><td>${c.id}</td><td>${new Date(c.creada).toLocaleString("es")}</td>
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

$("#form-etiquetas").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const r = await api("/api/etiquetas", { method: "POST", body: new FormData(e.target) });
    $("#res-etiquetas").textContent = `${r.actualizados} participantes actualizados` + (r.n_desconocidos ? `; ${r.n_desconocidos} IDs no encontrados (${r.desconocidos.slice(0, 5).join(", ")})` : "");
  } catch (err) { $("#res-etiquetas").textContent = err.message; }
};

// ---------- Navegación ----------

const cargadores = { resumen: cargarResumen, participantes: cargarParticipantes, perfiles: cargarCorridas, analisis: cargarAnalisis };
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
Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
mostrar(location.hash.slice(1));
