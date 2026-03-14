document.addEventListener('DOMContentLoaded', () => {
    const dataElement = document.getElementById('all-configs-data');
    // Если на странице нет данных конфигурации, проверяем только теорию и выходим
    if (!dataElement) {
        initTheoryNavigation();
        return;
    }

    const allConfigs = JSON.parse(dataElement.textContent);

    let activeProblems = [];
    let currentConfigId = null;
    let currentIdx = 0;
    let results = [];
    let startTime;
    let timerInterval;

    const elements = {
        setupScreen: document.getElementById('setupScreen'),
        workoutScreen: document.getElementById('workoutScreen'),
        modeInfo: document.getElementById('selectedModeInfo'),
        modeLabel: document.getElementById('currentModeLabel'),
        expression: document.getElementById('expression'),
        input: document.getElementById('userAnswer'),
        timer: document.getElementById('timer'),
        progressBar: document.getElementById('progressBar'),
        currentStep: document.getElementById('currentStep'),
        nextBtn: document.getElementById('nextBtn'),
        finishBtn: document.getElementById('finishEarlyBtn'),
        startBtn: document.getElementById('startWorkoutBtn')
    };

    // --- ИНИЦИАЛИЗАЦИЯ ТЕОРИИ ---
    initTheoryNavigation();

    // --- ГЛАВНАЯ ПРОВЕРКА ПРИ ЗАГРУЗКЕ ТРЕНАЖЕРА ---
    if (CONFIG_DATA.isAlreadyCompleted) {
        if (elements.setupScreen) elements.setupScreen.classList.add('opacity-50');
    }

    // --- ФУНКЦИИ ЛОГИКИ ТЕОРИИ ---
    function initTheoryNavigation() {
        const slides = document.querySelectorAll('.theory-slide');
        console.log("DEBUG: Найдено слайдов в DOM:", slides.length); // ДЕБАГ
        const totalSlides = slides.length;
        if (totalSlides === 0) return;

        let currentTheorySlide = 0;
        const nextSlideBtn = document.getElementById('next-slide');
        const prevSlideBtn = document.getElementById('prev-slide');
        const theoryProgress = document.getElementById('theory-progress');
        const stepBadge = document.getElementById('stepBadge');
        const finishTheoryBlock = document.getElementById('finishTheoryBlock');

        function updateTheorySlide(index) {
            slides.forEach((s, i) => {
                s.classList.toggle('d-none', i !== index);
            });

            if (totalSlides === 1) {
                if (prevSlideBtn) prevSlideBtn.classList.add('d-none');
                if (nextSlideBtn) nextSlideBtn.classList.add('d-none');
                if (finishTheoryBlock) finishTheoryBlock.classList.remove('d-none');
            } else {
                if (prevSlideBtn) {
                    prevSlideBtn.classList.remove('d-none');
                    prevSlideBtn.disabled = (index === 0);
                }
                if (nextSlideBtn) {
                    if (index === totalSlides - 1) {
                        nextSlideBtn.classList.add('d-none');
                        if (finishTheoryBlock) finishTheoryBlock.classList.remove('d-none');
                    } else {
                        nextSlideBtn.classList.remove('d-none');
                        if (finishTheoryBlock) finishTheoryBlock.classList.add('d-none');
                    }
                }
            }

            if (theoryProgress) {
                const percent = ((index + 1) / totalSlides) * 100;
                theoryProgress.style.width = percent + '%';
            }
            if (stepBadge) {
                stepBadge.innerText = `Шаг ${index + 1} из ${totalSlides}`;
            }
        }

        if (nextSlideBtn) nextSlideBtn.addEventListener('click', () => {
            if (currentTheorySlide < totalSlides - 1) {
                currentTheorySlide++;
                updateTheorySlide(currentTheorySlide);
            }
        });

        if (prevSlideBtn) prevSlideBtn.addEventListener('click', () => {
            if (currentTheorySlide > 0) {
                currentTheorySlide--;
                updateTheorySlide(currentTheorySlide);
            }
        });

        updateTheorySlide(0);

        // Кнопка "Я изучил материал"
        const markTheoryBtn = document.getElementById('markTheoryDone');
        if (markTheoryBtn) {
            markTheoryBtn.addEventListener('click', async function() {
                if (!CONFIG_DATA.assignmentId) return;
                this.disabled = true;
                this.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

                try {
                    const response = await fetch('/save_training_result/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CONFIG_DATA.csrfToken,
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: JSON.stringify({
                            homework_id: CONFIG_DATA.assignmentId,
                            is_theory_only: true
                        })
                    });
                    if (response.ok) window.location.reload();
                } catch (e) {
                    console.error(e);
                    this.disabled = false;
                    this.innerText = "✅ Я изучил материал";
                }
            });
        }
    }

    // --- ФУНКЦИИ ЛОГИКИ ТРЕНАЖЕРА (Твой оригинальный код) ---
    function initWorkout(configId) {
        if (CONFIG_DATA.presetConfigId && String(configId) !== String(CONFIG_DATA.presetConfigId)) {
            console.warn("Переключение режимов заблокировано.");
            return;
        }

        const configData = allConfigs[String(configId)];
        if (!configData) return;

        activeProblems = configData.problems;
        currentConfigId = configId;

        if (elements.modeLabel) elements.modeLabel.innerText = configData.label;
        if (elements.modeInfo) elements.modeInfo.classList.remove('d-none');

        document.querySelectorAll('.config-select-btn').forEach(btn => {
            if (btn.dataset.id === String(configId)) {
                btn.classList.remove('btn-outline-primary', 'btn-outline-warning');
                btn.classList.add(btn.classList.contains('exam-btn') ? 'btn-warning' : 'btn-primary', 'shadow-sm');
            } else {
                btn.classList.remove('btn-primary', 'btn-warning', 'shadow-sm');
                btn.classList.add(btn.classList.contains('exam-btn') ? 'btn-outline-warning' : 'btn-outline-primary');
            }
        });
    }

    function startWorkout() {
        if (CONFIG_DATA.isAlreadyCompleted || !activeProblems.length) return;
        elements.setupScreen.classList.add('d-none');
        elements.workoutScreen.classList.remove('d-none');
        window.scrollTo(0, 0);
        currentIdx = 0;
        results = [];
        startTime = new Date();
        startTimer();
        loadQuestion();
    }

    function loadQuestion() {
        if (currentIdx >= activeProblems.length) {
            finishTraining();
            return;
        }
        const q = activeProblems[currentIdx];
        elements.expression.innerText = q.question;
        elements.input.value = '';
        elements.input.focus();
        elements.currentStep.innerText = currentIdx + 1;
        elements.progressBar.style.width = `${(currentIdx / activeProblems.length) * 100}%`;
    }

    function handleNext() {
        const val = elements.input.value.trim();
        if (!val) return;
        results.push({
            q: activeProblems[currentIdx].question,
            user_a: val,
            correct_a: activeProblems[currentIdx].answer,
            is_correct: val === String(activeProblems[currentIdx].answer)
        });
        currentIdx++;
        loadQuestion();
    }

    function startTimer() {
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            let diff = Math.floor((new Date() - startTime) / 1000);
            elements.timer.innerText = `${Math.floor(diff/60).toString().padStart(2,'0')}:${(diff%60).toString().padStart(2,'0')}`;
        }, 1000);
    }

    // --- ЛОГИКА МОДАЛЬНОГО ОКНА (РЕЗУЛЬТАТЫ) ---
const showDetailsBtn = document.getElementById('showDetailsBtn');
const detailedResults = document.getElementById('detailedResults');
const detailsTableBody = document.getElementById('detailsTableBody');

if (showDetailsBtn) {
    showDetailsBtn.addEventListener('click', function() {
        // Переключаем видимость блока с таблицей
        detailedResults.classList.toggle('d-none');

        // Меняем текст кнопки в зависимости от состояния
        if (detailedResults.classList.contains('d-none')) {
            this.innerText = 'Подробнее';
        } else {
            this.innerText = 'Скрыть детали';
            renderDetailedTable(); // Отрисовываем таблицу
        }
    });
}

function renderDetailedTable() {
    if (!detailsTableBody) return;

    // Очищаем таблицу перед заполнением
    detailsTableBody.innerHTML = '';

    results.forEach((res, index) => {
        const row = document.createElement('tr');
        // Добавляем класс подсветки строки (зеленый/красный)
        row.className = res.is_correct ? 'table-success-light' : 'table-danger-light';

        row.innerHTML = `
            <td class="fw-medium">${res.q}</td>
            <td class="${res.is_correct ? 'text-success' : 'text-danger'} fw-bold">${res.user_a}</td>
            <td><span class="badge bg-success">${res.correct_a}</span></td>
            <td class="text-center">
                ${res.is_correct ? '<i class="bi bi-check-circle-fill text-success"></i>' : '<i class="bi bi-x-circle-fill text-danger"></i>'}
            </td>
        `;
        detailsTableBody.appendChild(row);
    });
}

    // События тренажера
    if (CONFIG_DATA.presetConfigId) initWorkout(CONFIG_DATA.presetConfigId);
    document.querySelectorAll('.config-select-btn').forEach(btn => {
        btn.addEventListener('click', () => { if(!btn.disabled) initWorkout(btn.dataset.id); });
    });
    if (elements.startBtn) elements.startBtn.addEventListener('click', startWorkout);
    if (elements.nextBtn) elements.nextBtn.addEventListener('click', handleNext);
    if (elements.input) elements.input.addEventListener('keypress', (e) => { if(e.key === 'Enter') handleNext(); });

    async function finishTraining() {
        clearInterval(timerInterval);
        const total = results.length;
        const correctCount = results.filter(r => r.is_correct).length;

        const modal = new bootstrap.Modal(document.getElementById('resultModal'));
        document.getElementById('resSolved').innerText = total;
        document.getElementById('resCorrectCount').innerText = correctCount;
        document.getElementById('resCorrectPercent').innerText = Math.round((correctCount/total)*100) + '%';
        document.getElementById('resTime').innerText = elements.timer.innerText;
        modal.show();

        if (CONFIG_DATA.isAuthenticated) {
            await fetch('/save_training_result/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': CONFIG_DATA.csrfToken, 'X-Requested-With': 'XMLHttpRequest'},
                body: JSON.stringify({
                    config_id: currentConfigId,
                    homework_id: CONFIG_DATA.assignmentId,
                    total: total,
                    correct: correctCount,
                    details: results
                })
            });
            const closeBtn = document.getElementById('closeModalBtn');
            if (closeBtn) {
                closeBtn.innerText = "Завершить";
                closeBtn.onclick = () => window.location.reload();
            }
        }
    }
});