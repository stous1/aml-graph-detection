/* Página "¿Forma o tamaño?": lee los JSON publicados y arma las tres pestañas. */
(function () {
  "use strict";
  var M = window.Motor;
  var R = "resultados/";
  var SVG = "http://www.w3.org/2000/svg";
  var NOMBRE_METODO = {
    regla: "Regla simple (tamaño)",
    forma: "Detector de forma, sin etiquetas",
    final: "Modelo final, con etiquetas"
  };
  var TEXTO_CATEGORIA = {
    acierto: "Alerta acertada", falsa_alarma: "Falsa alarma", no_detectado: "Lavado no detectado"
  };
  var VAR_FORMA = {
    novedad: "contrapartes nuevas", unicidad: "una transferencia por contraparte",
    homogeneidad: "montos parecidos", exclusividad: "contrapartes dedicadas",
    dispersion: "repartido en el tiempo"
  };

  function json(ruta) {
    return fetch(R + ruta).then(function (r) {
      if (!r.ok) throw new Error(ruta + ": " + r.status);
      return r.json();
    });
  }
  function el(tag, attrs, hijos) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (hijos || []).forEach(function (h) { if (h) e.appendChild(h); });
    return e;
  }
  function svg(tag, attrs) {
    var e = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function chips(contenedor, opciones, alElegir) {
    contenedor.innerHTML = "";
    opciones.forEach(function (o, i) {
      var b = el("button", { type: "button", "aria-pressed": String(i === 0), texto: o.texto });
      b.addEventListener("click", function () {
        contenedor.querySelectorAll("button").forEach(function (x) {
          x.setAttribute("aria-pressed", String(x === b));
        });
        alElegir(o.valor);
      });
      contenedor.appendChild(b);
    });
  }

  /* ---------- pestañas ---------- */
  var pestanas = ["forma", "monedas", "alertas"];
  var alMostrar = {};
  pestanas.forEach(function (p) {
    document.getElementById("tab-" + p).addEventListener("click", function () {
      pestanas.forEach(function (q) {
        document.getElementById("tab-" + q).setAttribute("aria-selected", String(q === p));
        document.getElementById("panel-" + q).hidden = q !== p;
      });
      if (alMostrar[p]) alMostrar[p]();
    });
  });

  /* ---------- redes en estrella ---------- */
  function dibujarEstrella(contenedor, nodos, centroEtiqueta, omitidos) {
    var ancho = 320, alto = 300, cx = ancho / 2, cy = alto / 2, escala = 120;
    var s = svg("svg", { viewBox: "0 0 " + ancho + " " + alto, class: "red", role: "img",
      "aria-label": "Red de " + nodos.length + " contrapartes alrededor de " + centroEtiqueta });
    var pos = M.estrella(nodos.length);
    var maxUsd = Math.max.apply(null, nodos.map(function (n) { return n.usd; }).concat([1]));
    nodos.forEach(function (n, i) {
      var x = cx + escala * pos[i].x, y = cy + escala * pos[i].y;
      s.appendChild(svg("line", { x1: cx, y1: cy, x2: x, y2: y,
        stroke: n.lavado ? "var(--lavado)" : "var(--nodo)", "stroke-width": n.lavado ? 2 : 1,
        "stroke-opacity": n.lavado ? 0.9 : 0.5 }));
    });
    nodos.forEach(function (n, i) {
      var x = cx + escala * pos[i].x, y = cy + escala * pos[i].y;
      var c = svg("circle", { cx: x, cy: y, r: 2.5 + 6 * Math.sqrt(n.usd / maxUsd),
        fill: n.lavado ? "var(--lavado)" : "var(--nodo)", stroke: "var(--papel)", "stroke-width": 1 });
      var t = svg("title", {});
      t.textContent = (n.etiqueta || "") + M.miles(n.n) + " transf. · " + M.usd(n.usd) + " USD" +
        (n.lavado ? " · lavado" : "");
      c.appendChild(t);
      s.appendChild(c);
    });
    s.appendChild(svg("circle", { cx: cx, cy: cy, r: 9, fill: "var(--texto)" }));
    if (omitidos > 0) {
      var tx = svg("text", { x: ancho - 6, y: alto - 8, "text-anchor": "end", "font-size": 12,
        fill: "var(--suave)" });
      tx.textContent = "+" + M.miles(omitidos) + " contrapartes más";
      s.appendChild(tx);
    }
    contenedor.appendChild(s);
  }

  /* ---------- pestaña 1: forma o tamaño ---------- */
  function casoTarjeta(caso, datos) {
    var t = el("div", { class: "tarjeta" });
    t.appendChild(el("h3", { texto: caso.lavado ? "Cuenta con lavado" : "Cuenta legítima" }));
    t.appendChild(el("p", { class: "sub", texto: "Cuenta " + caso.cuenta + " · " + caso.etiqueta }));
    var red = caso.red;
    var nodos = red.dibujo.map(function (n) { return { n: n.n, usd: n.usd, lavado: n.lavado }; });
    dibujarEstrella(t, nodos, "la cuenta " + caso.cuenta, red.contrapartes - nodos.length);
    var dl = el("dl", { class: "datos" });
    [["Contrapartes en 24 h", M.miles(caso.contrapartes_24h)],
     ["Esta estructura", M.miles(red.transferencias) + " transferencias " +
       (red.direccion === "salida" ? "enviadas" : "recibidas") + " a " + M.miles(red.contrapartes) + " cuentas"],
     ["Monto", M.usd(red.usd_total) + " USD"]].forEach(function (f) {
      dl.appendChild(el("dt", { texto: f[0] }));
      dl.appendChild(el("dd", { texto: f[1] }));
    });
    t.appendChild(dl);
    var puestos = el("div", { class: "puestos" });
    ["regla", "forma", "final"].forEach(function (m) {
      var p = caso.puesto[m];
      puestos.appendChild(el("div", { class: "puesto " + m }, [
        el("div", { class: "met", texto: NOMBRE_METODO[m] }),
        el("div", { class: "num", texto: p ? "n.º " + M.miles(p) : "—" })
      ]));
    });
    t.appendChild(puestos);
    t.appendChild(el("p", { class: "sub", texto: "Puesto entre " + M.miles(datos.cuentas_evaluadas) +
      " cuentas del período de prueba (1 = la más sospechosa para ese método)." }));
    // variables del detector de forma, con casillas para quitar o agregar
    var cfg = datos.config_forma, est = caso.estructura;
    t.appendChild(el("h3", { texto: "Por qué, según el detector de forma" }));
    var lista = el("ul", { class: "variables" });
    var puntaje = el("p", { class: "sub" });
    var elegidas = cfg.variables.slice();
    function actualizar() {
      var p = M.puntajeForma(est.variables, elegidas, cfg.tamano, est.n_contrapartes, datos.piso);
      puntaje.textContent = "Puntaje de forma con las variables marcadas: " + M.coma(p, 3) +
        (est.direccion !== cfg.direccion ? " (además, el detector solo mira abanicos de " +
          cfg.direccion + " y este es de " + est.direccion + ")" : "");
    }
    Object.keys(VAR_FORMA).forEach(function (v) {
      var id = "v-" + caso.cuenta + "-" + v;
      var casilla = el("input", { type: "checkbox", id: id });
      casilla.checked = elegidas.indexOf(v) >= 0;
      casilla.addEventListener("change", function () {
        elegidas = Object.keys(VAR_FORMA).filter(function (w) {
          return document.getElementById("v-" + caso.cuenta + "-" + w).checked;
        });
        actualizar();
      });
      var barra = el("div", { class: "barra" }, [el("span", {})]);
      barra.firstChild.style.width = (100 * est.variables[v]) + "%";
      lista.appendChild(el("li", {}, [casilla,
        el("label", { for: id }, [el("span", { texto: VAR_FORMA[v] }), barra]),
        el("span", { class: "num", texto: M.coma(est.variables[v], 2) })]));
    });
    t.appendChild(lista);
    t.appendChild(puntaje);
    actualizar();
    return t;
  }

  function pestanaForma(datos, curvas) {
    var a = datos.alerta, c = datos.comercio;
    document.getElementById("forma-lectura").textContent =
      "La regla simple ordena por tamaño: pone a la cuenta legítima con más contrapartes en el puesto " +
      M.miles(c.puesto.regla) + " y al abanico de lavado en el " + M.miles(a.puesto.regla) + ". " +
      "El detector de forma, sin etiquetas y sin mirar monedas, invierte el orden: abanico en el " +
      M.miles(a.puesto.forma) + ", concentrador en el " + (c.puesto.forma ? M.miles(c.puesto.forma) : "—") +
      ". Marca las casillas para ver qué variable hace la diferencia.";
    var casos = document.getElementById("casos");
    casos.appendChild(casoTarjeta(a, datos));
    casos.appendChild(casoTarjeta(c, datos));

    var variante = "hi";
    var deslizante = document.getElementById("k");
    function kMax() {
      return Math.min.apply(null, ["regla", "forma", "final"].map(function (m) {
        var cv = curvas[variante].metodos[m];
        return cv[cv.length - 1].k;
      }));
    }
    function pintar() {
      var k = M.kDesdeDeslizante(deslizante.value / 1000, 10, kMax());
      document.getElementById("k-texto").textContent = M.miles(k) + " de " +
        M.miles(curvas[variante].cuentas) + " (" + variante.toUpperCase() + ")";
      var cont = document.getElementById("curvas");
      cont.innerHTML = "";
      ["regla", "forma", "final"].forEach(function (m) {
        var p = M.precisionEnK(curvas[variante].metodos[m], k);
        cont.appendChild(el("div", { class: "serie " + m }, [
          el("div", { class: "met", texto: NOMBRE_METODO[m] }),
          el("div", { class: "grande", texto: M.pct(p, p < 0.1 ? 1 : 0) }),
          el("div", { class: "met", texto: "≈ " + M.miles(p * k) + " de " + M.miles(k) + " con lavado" })
        ]));
      });
    }
    deslizante.addEventListener("input", pintar);
    chips(document.getElementById("variante-curvas"),
      [{ texto: "HI", valor: "hi" }, { texto: "LI", valor: "li" }],
      function (v) { variante = v; pintar(); });
    pintar();
  }

  /* ---------- pestaña 2: el artefacto de las monedas ---------- */
  function pestanaMonedas(h2, h4, datos) {
    var pasos = [
      { id: "con", corto: "Hito 1, con monedas", fuente: h2, det: "abanicos_h1",
        texto: "El detector del hito 1: abanicos de salida puntuados por unicidad × mezcla de monedas." },
      { id: "sin", corto: "Sin la mezcla de monedas", fuente: h2, det: "abanicos_h1_sin_monedas",
        texto: "El mismo detector sin la mezcla de monedas. Casi todo dependía de esa huella del simulador." },
      { id: "forma", corto: "Forma pura", fuente: h2, det: "abanicos_salida_forma",
        texto: "Reconstruido en desarrollo solo con forma (contrapartes nuevas, una transferencia a cada una, montos parecidos). Recupera buena parte, sin moneda ni formato." },
      { id: "final", corto: "Con etiquetas", fuente: h4, det: "gnn_sin_coles",
        texto: "El modelo final: una red sobre el grafo entrenada con etiquetas de desarrollo, solo con variables estructurales." }
    ];
    var valor = function (p, v, campo) {
      var m = p.fuente.variantes[v][p.det];
      return campo === "p100" ? m.precision_k[0].precision : m.f1_transaccion.f1;
    };
    var con = pasos[0], sin = pasos[1];
    document.getElementById("monedas-lectura").textContent =
      "En el hito 1, un detector de abanicos puso " + Math.round(100 * valor(con, "hi", "p100")) +
      " de cada 100 alertas sobre cuentas ilícitas en HI. La señal decisiva era que el centro del abanico " +
      "paga en varias monedas. En AMLworld es así; en un banco de una sola moneda no existe. Sin esa señal, " +
      "cae a " + Math.round(100 * valor(sin, "hi", "p100")) + " de cada 100.";
    var pasosEl = document.getElementById("anim-pasos");
    pasos.forEach(function (p) { pasosEl.appendChild(el("span", { texto: p.corto })); });
    var barras = document.getElementById("anim-barras");
    var filas = {};
    barras.appendChild(el("div", { class: "leyenda" }, [
      el("span", {}, [el("i", { style: "background:var(--final)" }), document.createTextNode("HI")]),
      el("span", {}, [el("i", { style: "background:var(--regla)" }), document.createTextNode("LI")]),
      el("span", { texto: "Precisión en el top-100 de cuentas, período de prueba" })]));
    ["hi", "li"].forEach(function (v) {
      var span = el("span", {});
      var num = el("span", { class: "num" });
      barras.appendChild(el("div", { class: "anim-fila " + v }, [
        el("span", { texto: v.toUpperCase() }), el("div", { class: "barra" }, [span]), num]));
      filas[v] = { span: span, num: num };
    });
    var texto = document.getElementById("anim-texto");
    var temporizador = null;
    function mostrar(i) {
      var p = pasos[i];
      pasosEl.querySelectorAll("span").forEach(function (s, j) { s.className = j === i ? "activo" : ""; });
      ["hi", "li"].forEach(function (v) {
        var x = valor(p, v, "p100");
        filas[v].span.style.width = (100 * x) + "%";
        filas[v].num.textContent = M.coma(x, 2);
      });
      texto.textContent = p.texto + " F1 por transferencia: " + M.coma(valor(p, "hi", "f1"), 3) +
        " en HI y " + M.coma(valor(p, "li", "f1"), 3) + " en LI.";
    }
    function reproducir() {
      clearInterval(temporizador);
      var i = 0;
      mostrar(0);
      temporizador = setInterval(function () {
        i += 1;
        if (i >= pasos.length) { clearInterval(temporizador); return; }
        mostrar(i);
      }, 2200);
    }
    document.getElementById("anim-repetir").addEventListener("click", reproducir);
    var yaVista = false;
    alMostrar.monedas = function () { if (!yaVista) { yaVista = true; reproducir(); } };
    mostrar(0);
    var monedas = datos.alerta.red.monedas_pagadas;
    var nombres = Object.keys(monedas);
    document.getElementById("monedas-sub").textContent = "Las " + M.miles(datos.alerta.red.transferencias) +
      " transferencias del abanico de la cuenta " + datos.alerta.cuenta + " salen en " + nombres.length +
      (nombres.length === 1 ? " moneda" : " monedas distintas") +
      ". El detector de forma no lo sabe: no usa la moneda.";
    var cont = document.getElementById("monedas");
    nombres.forEach(function (n) { cont.appendChild(el("span", { texto: n + " · " + monedas[n] })); });
  }

  /* ---------- pestaña 3: explorador de alertas ---------- */
  function dibujarVecindario(contenedor, a) {
    var entran = a.vecinos.filter(function (v) { return v.direccion === "entrada"; });
    var salen = a.vecinos.filter(function (v) { return v.direccion === "salida"; });
    var ancho = 360, alto = 230, cx = ancho / 2, cy = alto / 2;
    var s = svg("svg", { viewBox: "0 0 " + ancho + " " + alto, class: "red", role: "img",
      "aria-label": "Vecindario: " + entran.length + " contrapartes que envían y " + salen.length + " que reciben" });
    var maxUsd = Math.max.apply(null, a.vecinos.map(function (v) { return v.usd; }).concat([1]));
    function lado(lista, signo) {
      lista.forEach(function (v, i) {
        var t = lista.length === 1 ? 0.5 : i / (lista.length - 1);
        var ang = (-0.42 + 0.84 * t) * Math.PI;
        var x = cx + signo * 140 * Math.cos(ang), y = cy + 95 * Math.sin(ang);
        s.appendChild(svg("line", { x1: cx, y1: cy, x2: x, y2: y,
          stroke: v.lavado ? "var(--lavado)" : "var(--nodo)", "stroke-width": v.lavado ? 2 : 1,
          "stroke-opacity": v.lavado ? 0.9 : 0.5 }));
        var c = svg("circle", { cx: x, cy: y, r: 2.5 + 5 * Math.sqrt(v.usd / maxUsd),
          fill: v.lavado ? "var(--lavado)" : "var(--nodo)" });
        var tt = svg("title", {});
        tt.textContent = "Cuenta " + v.contraparte + " · " + (signo < 0 ? "envía" : "recibe") + " · " +
          M.miles(v.n) + " transf. · " + M.usd(v.usd) + " USD" + (v.lavado ? " · lavado" : "");
        c.appendChild(tt);
        s.appendChild(c);
      });
    }
    lado(entran, -1);
    lado(salen, 1);
    s.appendChild(svg("circle", { cx: cx, cy: cy, r: 9, fill: "var(--texto)" }));
    [["recibe de", 8, "start"], ["envía a", ancho - 8, "end"]].forEach(function (e) {
      var t = svg("text", { x: e[1], y: 14, "text-anchor": e[2], "font-size": 12, fill: "var(--suave)" });
      t.textContent = e[0];
      s.appendChild(t);
    });
    contenedor.appendChild(s);
  }

  function dibujarFlujo(contenedor, flujo, pasoHoras) {
    var ancho = 360, alto = 184, margen = 18, medio = (alto - 14) / 2;
    var s = svg("svg", { viewBox: "0 0 " + ancho + " " + alto, class: "flujo", role: "img",
      "aria-label": "Dinero que entra y sale cada " + pasoHoras + " horas" });
    var max = Math.max.apply(null, flujo.map(function (f) { return Math.max(f.entra, f.sale); }).concat([1]));
    var inicio = new Date(flujo.length ? flujo[0].inicio.replace(" ", "T") : 0);
    var total = 5 * 24 / pasoHoras;
    var w = (ancho - 2 * margen) / total;
    s.appendChild(svg("line", { x1: margen, x2: ancho - margen, y1: medio, y2: medio, stroke: "var(--borde)" }));
    // marcas de día: la ventana tiene 5 días, del 6 al 10 de septiembre
    for (var dia = 0; dia < 5; dia++) {
      var xd = margen + dia * (24 / pasoHoras) * w;
      s.appendChild(svg("line", { x1: xd, x2: xd, y1: 6, y2: alto - 16, stroke: "var(--borde)", "stroke-dasharray": "2 3" }));
      var td = svg("text", { x: xd + 2, y: alto - 3, "font-size": 11, fill: "var(--suave)" });
      td.textContent = "día " + (6 + dia);
      s.appendChild(td);
    }
    flujo.forEach(function (f) {
      var i = Math.round((new Date(f.inicio.replace(" ", "T")) - inicio) / 36e5 / pasoHoras);
      var x = margen + i * w + 1;
      var he = (medio - 14) * f.entra / max, hs = (medio - 14) * f.sale / max;
      if (he > 0) s.appendChild(svg("rect", { x: x, y: medio - he, width: Math.max(w - 2, 1), height: he, fill: "var(--final)", rx: 2 }));
      if (hs > 0) s.appendChild(svg("rect", { x: x, y: medio, width: Math.max(w - 2, 1), height: hs, fill: "var(--regla)", rx: 2 }));
    });
    contenedor.appendChild(s);
    contenedor.appendChild(el("div", { class: "leyenda" }, [
      el("span", {}, [el("i", { style: "background:var(--final)" }), document.createTextNode("entra")]),
      el("span", {}, [el("i", { style: "background:var(--regla)" }), document.createTextNode("sale")]),
      el("span", { texto: "USD cada " + pasoHoras + " h, días 6 a 10" })]));
  }

  function detalle(a, datos) {
    var d = document.getElementById("detalle");
    d.innerHTML = "";
    var t = el("div", { class: "tarjeta" });
    t.appendChild(el("p", {}, [el("span", { class: "etiqueta-cat cat-" + a.categoria, texto: TEXTO_CATEGORIA[a.categoria] })]));
    t.appendChild(el("h3", { texto: "Cuenta " + a.cuenta + " · puesto " + M.miles(a.puesto) }));
    t.appendChild(el("p", { class: "sub", texto: (a.patrones.length ? "Lavado: " + a.patrones.join(", ") : "Sin lavado") +
      " · " + M.miles(a.transferencias) + " transferencias con " + M.miles(a.contrapartes) + " cuentas en la ventana" }));
    dibujarVecindario(t, a);
    if (a.vecinos_omitidos > 0) t.appendChild(el("p", { class: "sub", texto: "Se muestran las " + a.vecinos.length +
      " contrapartes principales; quedan " + M.miles(a.vecinos_omitidos) + " más." }));
    t.appendChild(el("h3", { texto: "El dinero en el tiempo" }));
    dibujarFlujo(t, a.flujo, datos.paso_horas);
    t.appendChild(el("h3", { texto: "Variables estructurales (percentil entre todas las cuentas)" }));
    var tabla = el("table", { class: "vars" });
    a.variables.forEach(function (v) {
      var raro = v.percentil >= 0.95 || v.percentil <= 0.05;
      var barra = el("div", { class: "barra" }, [el("span", {})]);
      barra.firstChild.style.width = (100 * v.percentil) + "%";
      tabla.appendChild(el("tr", raro ? { class: "raro" } : {}, [
        el("td", { texto: v.texto }), el("td", {}, [barra]),
        el("td", { class: "v", texto: M.pct(v.percentil) })]));
    });
    t.appendChild(tabla);
    t.appendChild(el("p", { class: "sub", texto: "En negrita, las variables en que la cuenta está entre el 5 % más alto o más bajo. " +
      "Muestran en qué es atípica; no son una explicación causal de la decisión de la red." }));
    d.appendChild(t);
  }

  function pestanaAlertas(alertas) {
    var variante = "hi", categoria = "acierto";
    function pintarLista() {
      var datos = alertas[variante];
      document.getElementById("alertas-lectura").textContent =
        "El modelo final marca el " + M.pct(datos.fraccion_alertas_cuentas, 2) + " de las cuentas de " +
        datos.variante + " (la misma fracción que dio el mejor F1 en desarrollo). Aquí están sus primeras " +
        "alertas acertadas, las falsas alarmas con más puntaje y las cuentas con lavado que no marcó.";
      var lista = document.getElementById("lista");
      lista.innerHTML = "";
      var cuentas = datos.cuentas.filter(function (a) { return a.categoria === categoria; });
      cuentas.forEach(function (a, i) {
        var b = el("button", { type: "button", "aria-pressed": String(i === 0) }, [
          el("span", { texto: "Cuenta " + a.cuenta }),
          el("span", { class: "num", texto: "n.º " + M.miles(a.puesto) }),
          el("span", { class: "det", texto: (a.patrones.length ? a.patrones.join(", ") : "sin lavado") +
            " · " + M.miles(a.contrapartes) + " contrapartes" })]);
        b.addEventListener("click", function () {
          lista.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
          detalle(a, datos);
        });
        lista.appendChild(b);
      });
      if (cuentas.length) detalle(cuentas[0], datos);
    }
    chips(document.getElementById("variante-alertas"), [{ texto: "HI", valor: "hi" }, { texto: "LI", valor: "li" }],
      function (v) { variante = v; pintarCategorias(); pintarLista(); });
    function pintarCategorias() {
      var datos = alertas[variante];
      chips(document.getElementById("categorias"), Object.keys(TEXTO_CATEGORIA).map(function (k) {
        var n = datos.cuentas.filter(function (a) { return a.categoria === k; }).length;
        return { texto: TEXTO_CATEGORIA[k] + " (" + n + ")", valor: k };
      }), function (c) { categoria = c; pintarLista(); });
      categoria = "acierto";
    }
    pintarCategorias();
    pintarLista();
  }

  Promise.all([
    json("demo/forma_tamano.json"), json("demo/curvas.json"), json("hito2/metricas.json"),
    json("hito4/metricas.json"), json("demo/alertas_hi.json"), json("demo/alertas_li.json")
  ]).then(function (r) {
    pestanaForma(r[0], r[1]);
    pestanaMonedas(r[2], r[3], r[0]);
    pestanaAlertas({ hi: r[4], li: r[5] });
    document.body.setAttribute("data-listo", "1");
  }).catch(function (e) {
    document.querySelector("main").prepend(el("p", { class: "aviso", texto: "No se pudieron cargar los datos: " + e }));
    console.error(e);
  });
})();
