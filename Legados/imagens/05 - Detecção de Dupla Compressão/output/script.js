document.addEventListener('DOMContentLoaded', () => {
    // Gerar uma lista de 64 páginas
    const pages = [];
    for (let i = 1; i <= 64; i++) {
        pages.push(`hist_${i}.html`);
        pages.push(`deteccao_${i}.html`);
    }

    let currentPage = 0;

    const contentDiv = document.getElementById('content');
    const prevButton = document.getElementById('prevButton');
    const nextButton = document.getElementById('nextButton');

    function loadPage(pageIndex) {
        if (pageIndex >= 0 && pageIndex < pages.length) {
            fetch(pages[pageIndex])
                .then(response => response.text())
                .then(html => {
                    contentDiv.innerHTML = html;
                    executeScripts(contentDiv);
                })
                .catch(error => {
                    contentDiv.innerHTML = `<p>Erro ao carregar a página: ${error}</p>`;
                });
        }
    }

    function executeScripts(element) {
        const scripts = element.getElementsByTagName('script');
        for (let i = 0; i < scripts.length; i++) {
            const script = document.createElement('script');
            script.text = scripts[i].text;
            document.head.appendChild(script).parentNode.removeChild(script);
        }
    }

    prevButton.addEventListener('click', () => {
        if (currentPage > 0) {
            currentPage--;
            loadPage(currentPage);
        }
    });

    nextButton.addEventListener('click', () => {
        if (currentPage < pages.length - 1) {
            currentPage++;
            loadPage(currentPage);
        }
    });

    // Carregar a primeira página na inicialização
    loadPage(currentPage);
});