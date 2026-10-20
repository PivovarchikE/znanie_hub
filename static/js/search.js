document.addEventListener('htmx:afterOnLoad', function(evt) {
    if (evt.detail.target.id === 'search-results') {
        const results = evt.detail.target;
        const input = document.querySelector('input[name="q"]');

        // Если есть текст и результаты не пусты
        if (input.value.trim().length > 0 && results.innerText.trim() !== "Ничего не найдено") {
            results.style.setProperty('display', 'block', 'important');
        } else if (input.value.trim().length > 0 && results.innerText.trim() === "Ничего не найдено") {
            results.style.setProperty('display', 'block', 'important');
        } else {
            results.style.display = 'none';
        }
    }
});

document.addEventListener('keydown', function(e) {
    const resultsContainer = document.getElementById('search-results');
    if (!resultsContainer || resultsContainer.style.display === 'none') return;

    const items = Array.from(resultsContainer.querySelectorAll('.dropdown-item'));
    let currentIndex = items.findIndex(item => item.classList.contains('active-result'));

    if (e.key === "ArrowDown") {
        e.preventDefault();
        if (items.length > 0) {
            if (currentIndex !== -1) items[currentIndex].classList.remove('active-result');
            currentIndex = (currentIndex + 1) % items.length;
            items[currentIndex].classList.add('active-result');
        }
    }
    else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (items.length > 0) {
            if (currentIndex !== -1) items[currentIndex].classList.remove('active-result');
            currentIndex = (currentIndex - 1 + items.length) % items.length;
            items[currentIndex].classList.add('active-result');
        }
    }
    else if (e.key === "Enter") {
        if (currentIndex !== -1) {
            const activeItem = items[currentIndex];
            const url = activeItem.getAttribute('href');
            if (url && url !== '#') {
                e.preventDefault();
                window.location.href = url;
            }
        }
        // Если ничего не выбрано стрелками, Enter сработает как обычная отправка формы
    }
    else if (e.key === "Escape") {
        resultsContainer.style.display = 'none';
    }
});

// Закрытие при клике ВНЕ формы
document.addEventListener('click', function(e) {
    const searchForm = document.querySelector('form[role="search"]');
    const results = document.getElementById('search-results');
    if (results && searchForm && !searchForm.contains(e.target)) {
        results.style.display = 'none';
    }
});