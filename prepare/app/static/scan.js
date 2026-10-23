/* Prepare - barcode scanning.
 *
 * Live camera: the browser's own BarcodeDetector where it exists (Chrome on
 * Android), otherwise ZXing (bundled, loaded only when needed - Safari on iPhone).
 * Browsers only allow the camera on https, so on the plain http address the
 * photo button does the same job from a still picture.
 * UK groceries use EAN-13 (and EAN-8 on small own-label packs); UPC covers
 * imported American goods.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var BASE = me.dataset.base || "";
  var ZXING_URL = me.dataset.zxing;
  var FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

  var $ = function (id) { return document.getElementById(id); };
  var video = $("video"), finder = $("viewfinder"), status = $("scan-status");
  var startBtn = $("start-camera"), stopBtn = $("stop-camera");
  var form = $("product"), msg = $("lookup-msg");
  var stream = null, detector = null, zxReader = null, zxControls = null, running = false, busy = false;

  var canLive = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  if (!canLive) { startBtn.hidden = true; $("http-note").hidden = false; }

  function say(text) { status.textContent = text; }

  function loadZXing() {
    if (window.ZXing) return Promise.resolve(window.ZXing);
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = ZXING_URL; s.onload = function () { resolve(window.ZXing); }; s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // TRY_HARDER helps with a still photo but stops ZXing finding anything in a
  // live video stream (tested), so it is only used for photos.
  function zxingHints(ZX, hard) {
    var hints = new Map();
    hints.set(ZX.DecodeHintType.POSSIBLE_FORMATS, [ZX.BarcodeFormat.EAN_13, ZX.BarcodeFormat.EAN_8, ZX.BarcodeFormat.UPC_A, ZX.BarcodeFormat.UPC_E]);
    if (hard) hints.set(ZX.DecodeHintType.TRY_HARDER, true);
    return hints;
  }

  async function nativeDetector() {
    if (!("BarcodeDetector" in window)) return null;
    try {
      var supported = await window.BarcodeDetector.getSupportedFormats();
      var wanted = FORMATS.filter(function (f) { return supported.indexOf(f) >= 0; });
      return wanted.length ? new window.BarcodeDetector({ formats: wanted }) : null;
    } catch (e) { return null; }
  }

  async function start() {
    if (running) return;
    form.hidden = true;
    finder.hidden = false; startBtn.hidden = true; stopBtn.hidden = false;
    say("Starting the camera…");
    running = true;
    try {
      detector = await nativeDetector();
      if (detector) {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false });
        video.srcObject = stream; await video.play();
        say("Looking for a barcode…");
        loop();
      } else {
        var ZX = await loadZXing();
        zxReader = new ZX.BrowserMultiFormatReader(zxingHints(ZX, false), 250);
        say("Looking for a barcode…");
        zxControls = zxReader.decodeFromConstraints({ video: { facingMode: { ideal: "environment" } } }, video, function (result) {
          if (result && running) found(result.getText());
        });
      }
    } catch (e) {
      stop();
      say(e && e.name === "NotAllowedError" ? "Camera permission was refused. Allow the camera for this site, or use a photo instead." : "Couldn't start the camera. Use a photo or type the barcode instead.");
    }
  }

  async function loop() {
    if (!running || !detector) return;
    try {
      var codes = await detector.detect(video);
      if (codes.length) { found(codes[0].rawValue); return; }
    } catch (e) { /* frame not ready */ }
    setTimeout(loop, 150);
  }

  function stop() {
    running = false;
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    if (zxReader) { try { zxReader.reset(); } catch (e) {} zxReader = null; }
    video.srcObject = null;
    finder.hidden = true; stopBtn.hidden = true; startBtn.hidden = !canLive;
  }

  function found(code) {
    if (busy) return;
    stop();
    if (navigator.vibrate) navigator.vibrate(60);
    lookup(code);
  }

  async function fromPhoto(file) {
    say("Reading the photo…");
    try {
      var det = await nativeDetector();
      if (det) {
        var bmp = await createImageBitmap(file);
        var codes = await det.detect(bmp);
        if (codes.length) return found(codes[0].rawValue);
      }
      var ZX = await loadZXing();
      var reader = new ZX.BrowserMultiFormatReader(zxingHints(ZX, true));
      var url = URL.createObjectURL(file);
      try { var r = await reader.decodeFromImageUrl(url); return found(r.getText()); }
      finally { URL.revokeObjectURL(url); }
    } catch (e) {
      say("Couldn't find a barcode in that photo. Get closer, keep it flat and well lit, or type the number.");
    }
  }

  function setUnit() {
    var opt = $("f-cat").selectedOptions[0];
    var unit = opt ? opt.dataset.unit : "";
    var food = $("f-cat").value === "food";
    var role = form.querySelector("input[name=role]:checked");
    $("unit-label").textContent = food ? (role && role.value !== "meal" ? "portions" : "meals") : unit;
    $("each-hint").hidden = !food;
    form.querySelector("[data-food-only]").hidden = !food;
  }

  async function lookup(code) {
    busy = true;
    say("Looking up " + code + "…");
    var data;
    try {
      var res = await fetch(BASE + "/api/lookup/" + encodeURIComponent(code));
      data = await res.json();
    } catch (e) {
      data = { ok: true, found: false, barcode: code.replace(/\D/g, ""), message: "Can't reach Prepare right now. Fill it in by hand." };
    }
    busy = false;
    if (!data.ok) { say(data.error); startBtn.hidden = !canLive; return; }
    say("");
    form.reset();
    $("f-loc").value = $("f-loc").defaultValue;
    $("f-barcode").value = data.barcode; $("p-code").textContent = data.barcode;
    $("f-source").value = data.found ? data.source : "manual";
    $("f-qtext").value = data.quantity_text || "";
    $("f-image").value = data.image_url || "";
    var img = $("p-img");
    if (data.image_url && navigator.onLine) { img.src = data.image_url; img.hidden = false; } else { img.hidden = true; img.removeAttribute("src"); }
    if (data.found) {
      $("f-generic").value = data.generic || "";
      $("f-name").value = data.name || "";
      $("f-brand").value = data.brand || "";
      $("f-cat").value = data.category || "food";
      $("f-each").value = data.pack_amount || 1;
      var r = form.querySelector("input[name=role][value='" + (data.role || "meal") + "']");
      if (r) r.checked = true;
      msg.textContent = data.saved ? "Known product — saved on this app." : "Found in " + data.source_name + ". Check the details, then add the date.";
      msg.className = "lookup-msg good";
    } else {
      $("f-cat").value = "food";
      msg.textContent = data.message;
      msg.className = "lookup-msg warn";
    }
    setUnit();
    form.hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    (data.found && data.generic ? $("f-bb") : $("f-generic")).focus({ preventScroll: true });
  }

  startBtn.addEventListener("click", start);
  stopBtn.addEventListener("click", function () { stop(); say("Camera off."); });
  $("photo").addEventListener("change", function (e) { if (e.target.files[0]) fromPhoto(e.target.files[0]); e.target.value = ""; });
  $("manual").addEventListener("submit", function (e) { e.preventDefault(); var c = $("code").value.trim(); if (c) lookup(c); });
  $("f-cat").addEventListener("change", setUnit);
  form.querySelectorAll("input[name=role]").forEach(function (r) { r.addEventListener("change", setUnit); });
  $("cancel").addEventListener("click", function () { form.hidden = true; say(""); if (canLive) startBtn.hidden = false; });
  document.querySelectorAll(".stepper button").forEach(function (b) {
    b.addEventListener("click", function () {
      var input = $("f-packs"); input.value = Math.max(0, (parseInt(input.value, 10) || 0) + parseInt(b.dataset.step, 10));
    });
  });
  window.addEventListener("pagehide", stop);
  setUnit();
  // Straight after adding one, carry on scanning if the camera is already allowed.
  if (me.dataset.autostart && canLive && navigator.permissions) {
    navigator.permissions.query({ name: "camera" }).then(function (p) { if (p.state === "granted") start(); }).catch(function () {});
  }
})();
