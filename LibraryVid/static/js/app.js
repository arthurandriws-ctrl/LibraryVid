(function () {
  const applyLoader = () => {
    const loader = document.getElementById('app-loader');
    const loaderText = document.getElementById('app-loader-text');
    if (!loader) return;

    const setText = (text) => {
      if (loaderText) loaderText.textContent = text;
    };

    document.body.classList.add('page-ready');

    const markLoading = (text = 'Carregando…') => {
      setText(text);
      loader.classList.remove('hidden');
      loader.classList.add('flex');
      document.body.classList.add('loading');
    };

    const markIdle = () => {
      loader.classList.add('hidden');
      loader.classList.remove('flex');
      document.body.classList.remove('loading');
    };

    window.addEventListener('pageshow', () => setTimeout(markIdle, 180));

    document.querySelectorAll('a[href]').forEach((link) => {
      const href = link.getAttribute('href') || '';
      const isExternal = href.startsWith('http') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('#') || link.target === '_blank';
      if (!isExternal && href) {
        link.addEventListener('click', () => {
          document.body.classList.add('page-transitioning');
          markLoading('Abrindo tela…');
        });
      }
    });

    document.querySelectorAll('form').forEach((form) => {
      form.addEventListener('submit', () => {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
          submitButton.disabled = true;
          submitButton.classList.add('opacity-70', 'cursor-wait');
        }

        const formName = form.getAttribute('data-loading-label') || 'Processando pedido…';
        const inputQuery = form.querySelector('input[name="q"]');
        if (inputQuery && form.getAttribute('action') && form.getAttribute('action').includes('/search')) {
          markLoading('Procurando resultados…');
        } else {
          markLoading(formName);
        }
      });
    });

    window.addEventListener('load', () => {
      setTimeout(markIdle, 180);
    });
  };

  const injectStyles = () => {
    const style = document.createElement('style');
    style.textContent = `
      body.page-transitioning { opacity: 0.96; transition: opacity 180ms ease; }
      body.page-ready { animation: pageFadeIn 240ms ease-out; }
      @keyframes pageFadeIn {
        from { opacity: 0.86; }
        to { opacity: 1; }
      }
    `;
    document.head.appendChild(style);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      injectStyles();
      applyLoader();
    });
  } else {
    injectStyles();
    applyLoader();
  }
})();
