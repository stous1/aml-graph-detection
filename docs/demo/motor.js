/*
 * Cálculos de la página interactiva, sin acceso al DOM. Funciona en el navegador (window.Motor)
 * y en Node (module.exports), para que tests/test_demo.py lo compare con Python.
 */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) {
    module.exports = fabrica();
  } else {
    raiz.Motor = fabrica();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /** Número con coma decimal, como en el resto del proyecto. */
  function coma(x, d) {
    var s = Math.abs(x).toFixed(d).replace(".", ",");
    return (x < 0 && Number(Math.abs(x).toFixed(d)) !== 0 ? "−" : "") + s;
  }

  /** Separador de miles con punto: 12538 -> "12.538". */
  function miles(n) {
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  /** Proporción como porcentaje entero o con decimales: 0,91 -> "91 %". */
  function pct(x, d) {
    return coma(x * 100, d === undefined ? 0 : d) + " %";
  }

  /** Dinero en USD abreviado: 1.234.567 -> "1,2 M". */
  function usd(x) {
    if (x >= 1e6) return coma(x / 1e6, 1) + " M";
    if (x >= 1e3) return coma(x / 1e3, 1) + " mil";
    return coma(x, 0);
  }

  /**
   * Puntaje de forma de una estructura: tamaño × producto de las variables elegidas, con piso.
   * Misma fórmula que lavado.demo.puntaje_forma y detectores.abanicos.puntuar_estructuras.
   */
  function puntajeForma(variables, usadas, tamano, nContrapartes, piso) {
    if (nContrapartes < 3) return 0;
    var base = tamano === "log2" ? Math.log2(nContrapartes)
      : tamano === "lineal" ? nContrapartes : 1;
    usadas.forEach(function (v) { base *= Math.max(variables[v], piso); });
    return base;
  }

  /**
   * Precisión en el top-k interpolada linealmente entre los puntos publicados de la curva
   * (exacta en esos puntos). Misma fórmula que lavado.demo.precision_interpolada.
   */
  function precisionEnK(curva, k) {
    if (k <= curva[0].k) return curva[0].precision;
    var ultimo = curva[curva.length - 1];
    if (k >= ultimo.k) return ultimo.precision;
    for (var i = 1; i < curva.length; i++) {
      if (k <= curva[i].k) {
        var a = curva[i - 1], b = curva[i];
        var t = (k - a.k) / (b.k - a.k);
        return a.precision + t * (b.precision - a.precision);
      }
    }
    return ultimo.precision;
  }

  /** Control deslizante en escala logarítmica: t en [0, 1] -> k entero en [kMin, kMax]. */
  function kDesdeDeslizante(t, kMin, kMax) {
    return Math.round(Math.exp(Math.log(kMin) + t * (Math.log(kMax) - Math.log(kMin))));
  }

  /**
   * Disposición radial determinista de n contrapartes alrededor del centro (0, 0): anillos de
   * hasta 24 puntos, cada uno más lejos. Devuelve [{x, y}] en coordenadas de -1 a 1.
   */
  function estrella(n) {
    var puntos = [], porAnillo = 24, anillos = Math.max(1, Math.ceil(n / porAnillo));
    for (var i = 0; i < n; i++) {
      var anillo = Math.floor(i / porAnillo);
      var enAnillo = Math.min(porAnillo, n - anillo * porAnillo);
      var angulo = (2 * Math.PI * (i % porAnillo)) / enAnillo - Math.PI / 2 + anillo * 0.13;
      var radio = 0.55 + (0.4 * (anillo + 1)) / anillos;
      puntos.push({ x: radio * Math.cos(angulo), y: radio * Math.sin(angulo) });
    }
    return puntos;
  }

  return {
    coma: coma, miles: miles, pct: pct, usd: usd, puntajeForma: puntajeForma,
    precisionEnK: precisionEnK, kDesdeDeslizante: kDesdeDeslizante, estrella: estrella
  };
});
