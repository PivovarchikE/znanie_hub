document.addEventListener('DOMContentLoaded', () => {
    const dataElement = document.getElementById('all-configs-data');
    if (!dataElement) return;

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

    // --- ГЛАВНАЯ ПРОВЕРКА ПРИ ЗАГРУЗКЕ ---
    if (CONFIG_DATA.isAlreadyCompleted) {
        // Сразу прячем всё лишнее
        if (elements.setupScreen) elements.setupScreen.classList.add('d-none');
        if (elements.workoutScreen) elements.workoutScreen.classList.add('d-none');

        alert("Вы уже выполнили это задание.");


        return; // ПРЕКРАЩАЕМ выполнение скрипта
    }

    // Если не пройдено — продолжаем обычную работу
    if (CONFIG_DATA.presetConfigId) {
        initWorkout(CONFIG_DATA.presetConfigId);
    }

    // --- ФУНКЦИИ ЛОГИКИ ---

    function initWorkout(configId) {
        const configData = allConfigs[String(configId)];
        if (!configData) return;

        activeProblems = configData.problems;
        currentConfigId = configId;

        // Если зашли из ДЗ (есть presetConfigId), сразу скрываем настройки и стартуем
        if (CONFIG_DATA.presetConfigId) {
            startWorkout();
        } else {
            // Иначе просто показываем инфо о выбранном режиме на экране настроек
            elements.modeLabel.innerText = configData.label;
            elements.modeInfo.classList.remove('d-none');
        }
    }

    function startWorkout() {
        if (CONFIG_DATA.isAlreadyCompleted) {
            alert("Вы уже выполнили это задание.");
            window.location.href = "/dashboard/"; // Перенаправляем
            return;
        }

        if (activeProblems.length === 0) return;

        elements.setupScreen.classList.add('d-none');
        elements.workoutScreen.classList.remove('d-none');

        currentIdx = 0;
        results = [];
        startTime = new Date();

        startTimer();
        loadQuestion();
    }

    // --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ ---

    // Проверяем, пришел ли ученик из ДЗ
    if (CONFIG_DATA.presetConfigId) {
        console.log("Автозапуск для конфига:", CONFIG_DATA.presetConfigId);
        initWorkout(CONFIG_DATA.presetConfigId);
    }

    // --- ОБРАБОТЧИКИ СОБЫТИЙ ---

    // Кнопки выбора сложности (ручной выбор)
    document.querySelectorAll('.config-select-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.config-select-btn').forEach(b =>
                b.classList.replace('btn-primary', 'btn-outline-primary'));
            this.classList.replace('btn-outline-primary', 'btn-primary');

            initWorkout(this.dataset.id);
        });
    });

    // Кнопка "Начать" на экране настроек
    elements.startBtn.addEventListener('click', startWorkout);

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

        // Обновление прогресс-бара
        const progress = (currentIdx / activeProblems.length) * 100;
        elements.progressBar.style.width = `${progress}%`;
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
            let m = Math.floor(diff / 60).toString().padStart(2, '0');
            let s = (diff % 60).toString().padStart(2, '0');
            elements.timer.innerText = `${m}:${s}`;
        }, 1000);
    }

    elements.nextBtn.addEventListener('click', handleNext);
    elements.input.addEventListener('keypress', (e) => { if(e.key === 'Enter') handleNext(); });
    elements.finishBtn.addEventListener('click', () => {
        if(confirm("Завершить тренировку досрочно?")) finishTraining();
    });

    async function finishTraining() {
        clearInterval(timerInterval);

        const total = results.length;
        const correctCount = results.filter(r => r.is_correct).length;
        const timeStr = elements.timer.innerText;
        const percent = total > 0 ? Math.round((correctCount / total) * 100) : 0;

        // Обновление модалки
        document.getElementById('resSolved').innerText = total;
        document.getElementById('resCorrectCount').innerText = correctCount;
        document.getElementById('resCorrectPercent').innerText = percent + '%';
        document.getElementById('resTime').innerText = timeStr;

        const modal = new bootstrap.Modal(document.getElementById('resultModal'));
        modal.show();

        // Обработка кнопки "Подробнее" в модалке
        const detailsBtn = document.getElementById('showDetailsBtn');
        if (detailsBtn) {
            detailsBtn.classList.remove('d-none');
            detailsBtn.onclick = function() {
                const tableBody = document.getElementById('detailsTableBody');
                tableBody.innerHTML = results.map(res => `
                    <tr>
                        <td>${res.q}</td>
                        <td class="${res.is_correct ? 'text-success' : 'text-danger fw-bold'}">${res.user_a}</td>
                        <td><span class="badge bg-secondary">${res.correct_a}</span></td>
                        <td>${res.is_correct ? '✅' : '❌'}</td>
                    </tr>
                `).join('');
                document.getElementById('detailedResults').classList.remove('d-none');
                this.classList.add('d-none');
            };
        }

        // Сохранение в БД
        if (CONFIG_DATA.isAuthenticated) {
            try {
                const response = await fetch('/save_training_result/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CONFIG_DATA.csrfToken
                    },
                    body: JSON.stringify({
                        config_id: currentConfigId,
                        homework_id: CONFIG_DATA.assignmentId, // Передаем ID домашки
                        total: total,
                        correct: correctCount,
                        details: results
                    })
                });
                if (!response.ok) throw new Error("Ошибка сервера");
            } catch (error) {
                console.error("Ошибка сохранения:", error);
            }
        }
    }
});