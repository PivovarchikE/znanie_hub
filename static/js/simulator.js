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
        startBtn: document.getElementById('startWorkoutBtn'),
        totalSteps: document.getElementById('totalSteps'),
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

    // --- ФУНКЦИИ ЛОГИКИ ТРЕНАЖЕРА ---
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

    let starting = false;

    async function startWorkout() {
        if (CONFIG_DATA.isAlreadyCompleted || starting || !currentConfigId) return;
        starting = true;
        try {
            const conf = allConfigs[String(currentConfigId)];
            if (conf && conf.picker) {
                if (!window.TaskPicker) {
                    alert('Не загрузился модуль выбора заданий. Обновите страницу (Ctrl+F5).');
                    return;
                }
                const fresh = await window.TaskPicker.fetchProblems(currentConfigId);
                if (!fresh) return;
                conf.problems = fresh;
                activeProblems = fresh;
            }
            if (!activeProblems.length) return;

            elements.setupScreen.classList.add('d-none');
            elements.workoutScreen.classList.remove('d-none');
            currentIdx = 0;
            results = [];
            startTime = new Date();
            if (elements.totalSteps) elements.totalSteps.innerText = activeProblems.length;
            startTimer();
            loadQuestion();
            // Показываем экран тренировки с самого верха (шапка + задание + поле ввода),
            // а не прокручиваем страницу к баннеру
            elements.workoutScreen.scrollIntoView({ block: 'start' });
        } finally {
            starting = false;
        }
    }

    function loadQuestion() {
        if (currentIdx >= activeProblems.length) {
            finishTraining();
            return;
        }
        const q = activeProblems[currentIdx];
        elements.expression.innerText = q.question;
        elements.input.value = '';
        // preventScroll: фокус не должен сам прокручивать страницу
        elements.input.focus({ preventScroll: true });
        elements.currentStep.innerText = currentIdx + 1;
        elements.progressBar.style.width = `${(currentIdx / activeProblems.length) * 100}%`;
    }

    function sameAnswer(user, correct) {
        const u = String(user).trim().replace(',', '.');
        const c = String(correct).trim();
        if (u !== '' && !isNaN(u) && !isNaN(c)) return Number(u) === Number(c);
        return u === c;
    }

    function handleNext() {
        const val = elements.input.value.trim();
        if (!val) return;
        results.push({
            q: activeProblems[currentIdx].question,
            user_a: val,
            correct_a: activeProblems[currentIdx].answer,
            is_correct: sameAnswer(val, activeProblems[currentIdx].answer)
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

    // --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ ---
    if (CONFIG_DATA.presetConfigId) {
        initWorkout(CONFIG_DATA.presetConfigId);
    } else {
        const selectBtns = document.querySelectorAll('.config-select-btn');
        if (selectBtns.length === 0) {
            // Если кнопок выбора нет (Таблица умножения / Умножение и деление),
            // автоматически инициализируем конфиг с пикером, чтобы currentConfigId не был null.
            const pickerConfigId = Object.keys(allConfigs).find(id => allConfigs[id].picker);
            if (pickerConfigId) {
                initWorkout(pickerConfigId);
            }
        }
    }

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

        // 1. Заполняем таблицу подробных результатов
        const tbody = document.getElementById('detailsTableBody');
        if (tbody) {
            tbody.innerHTML = results.map(r => `
                <tr>
                    <td>${r.q}</td>
                    <td>${r.user_a}</td>
                    <td>${r.correct_a}</td>
                    <td class="text-center">${r.is_correct ? '✅' : '❌'}</td>
                </tr>
            `).join('');
        }

        const modal = new bootstrap.Modal(document.getElementById('resultModal'));
        document.getElementById('resSolved').innerText = total;
        document.getElementById('resCorrectCount').innerText = correctCount;
        document.getElementById('resCorrectPercent').innerText = (total ? Math.round((correctCount/total)*100) : 0) + '%';
        document.getElementById('resTime').innerText = elements.timer.innerText;
        modal.show();

        // 2. Настраиваем кнопку «Подробнее» для переключения видимости отчета
        const showDetailsBtn = document.getElementById('showDetailsBtn');
        const detailedResults = document.getElementById('detailedResults');
        if (showDetailsBtn && detailedResults) {
            // Сбрасываем состояние при открытии модального окна
            detailedResults.classList.add('d-none');
            showDetailsBtn.innerText = 'Подробнее';

            // Удаляем старые обработчики во избежание дублирования и вешаем новый
            showDetailsBtn.onclick = () => {
                const isHidden = detailedResults.classList.contains('d-none');
                detailedResults.classList.toggle('d-none');
                showDetailsBtn.innerText = isHidden ? 'Скрыть' : 'Подробнее';
            };
        }

        if (CONFIG_DATA.isAuthenticated) {
            let saved = false;
            try {
                const res = await fetch('/save_training_result/', {
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
                saved = res.ok;
            } catch (e) { console.error(e); }

            if (!saved) {
                alert('Не удалось сохранить результат. Проверьте соединение и попробуйте снова.');
            }
            const closeBtn = document.getElementById('closeModalBtn');
            if (closeBtn) {
                closeBtn.innerText = "Завершить";
                closeBtn.onclick = () => window.location.reload();
            }
        }
    }
});