/* Content is visible by default. Reveals add movement only after an element
   enters view, so unsupported APIs and disabled JavaScript need no fallback. */
(() => {
  if (!('matchMedia' in window)) return;
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const targets = document.querySelectorAll('[data-reveal]');

  if (!('IntersectionObserver' in window) || !('animate' in Element.prototype)) {
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;

      observer.unobserve(entry.target);
      // Do not animate a section that already contains keyboard focus.
      if (motionPreference.matches || entry.target.contains(document.activeElement)) return;

      entry.target.animate(
        [
          { opacity: 0.75, transform: 'translateY(8px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        { duration: 450, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
      );
    });
  }, { threshold: 0.1 });

  targets.forEach((target) => observer.observe(target));

  // If the preference changes while the page is open, stop active reveals.
  if ('addEventListener' in motionPreference && 'getAnimations' in Element.prototype) {
    motionPreference.addEventListener('change', (event) => {
      if (event.matches) targets.forEach((target) => target.getAnimations().forEach((animation) => animation.cancel()));
    });
  }
})();
