/**
 * Interruptor elástico (estilo spring) — equivalente vanilla de ElasticSwitch + framer-motion.
 */
(function (global) {
  const SPRING_EASING = 'cubic-bezier(0.22, 1.12, 0.48, 1)';

  function syncAria(input) {
    input.setAttribute('aria-checked', input.checked ? 'true' : 'false');
  }

  function bounceThumb(input) {
    const track = input.nextElementSibling;
    const thumb = track?.querySelector('.elastic-switch__thumb');
    if (!thumb || typeof thumb.animate !== 'function') return;

    thumb.getAnimations().forEach((anim) => anim.cancel());
    thumb.animate(
      [
        { transform: 'scale(1)' },
        { transform: 'scale(1.14)' },
        { transform: 'scale(0.96)' },
        { transform: 'scale(1)' },
      ],
      { duration: 460, easing: SPRING_EASING },
    );
  }

  function bind(root = document) {
    root.querySelectorAll('.elastic-switch input[type="checkbox"]').forEach((input) => {
      if (input.dataset.elasticBound) return;
      input.dataset.elasticBound = '1';
      syncAria(input);

      input.addEventListener('change', () => {
        syncAria(input);
        bounceThumb(input);
      });
    });
  }

  global.HeimdallElasticSwitch = { bind, bounceThumb, syncAria };
})(window);
