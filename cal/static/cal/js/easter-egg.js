// ── Konami Code Easter Egg ──────────────────────────────────────
(function() {
  var KONAMI = [38,38,40,40,37,39,37,39,66,65];
  var pos = 0;
  var overlay = document.getElementById('easter-egg');
  var canvas = document.getElementById('starfield-canvas');
  var animFrame = null;

  function startStarfield() {
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    var stars = [];
    var cx = canvas.width / 2, cy = canvas.height / 2;
    for (var i = 0; i < 400; i++) {
      stars.push({
        x: (Math.random() - 0.5) * canvas.width * 2,
        y: (Math.random() - 0.5) * canvas.height * 2,
        z: Math.random() * canvas.width
      });
    }

    function draw() {
      ctx.fillStyle = 'rgba(0,0,0,0.15)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        s.z -= 6;
        if (s.z <= 0) {
          s.x = (Math.random() - 0.5) * canvas.width * 2;
          s.y = (Math.random() - 0.5) * canvas.height * 2;
          s.z = canvas.width;
        }
        var sx = (s.x / s.z) * cx + cx;
        var sy = (s.y / s.z) * cy + cy;
        var r = Math.max(0, (1 - s.z / canvas.width) * 3);
        var bright = Math.max(0, (1 - s.z / canvas.width));
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fillStyle = i % 2 === 0
          ? 'rgba(94,174,255,' + bright + ')'
          : 'rgba(192,132,252,' + bright + ')';
        ctx.fill();
      }
      animFrame = requestAnimationFrame(draw);
    }
    draw();
  }

  function stopStarfield() {
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
    if (canvas) {
      var ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }

  function show() {
    overlay.classList.add('show');
    startStarfield();
  }

  function hide() {
    overlay.classList.remove('show');
    stopStarfield();
  }

  document.addEventListener('keydown', function(e) {
    if (overlay.classList.contains('show')) {
      hide();
      return;
    }
    if (e.keyCode === KONAMI[pos]) {
      pos++;
      if (pos === KONAMI.length) {
        show();
        pos = 0;
      }
    } else {
      pos = e.keyCode === KONAMI[0] ? 1 : 0;
    }
  });

  overlay.addEventListener('click', hide);
})();
