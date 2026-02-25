document.addEventListener('DOMContentLoaded', () => {
    const dataElement = document.getElementById('all-configs-data');
    if (!dataElement) return;

    // Теперь здесь будет чистый объект, а не строка
    const allConfigs = JSON.parse(dataElement.textContent);

    let activeProblems = [];
    let currentConfigId = null;
    let currentIdx = 0;
    let results = [];
    let startTime;
    let timerInterval;

    // Создаем объект elements, чтобы не было ошибки "not defined"
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
        finishBtn: document.getElementById('finishEarlyBtn')
    };

    // ВЫБОР СЛОЖНОСТИ
    document.querySelectorAll('.config-select-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.config-select-btn').forEach(b => b.classList.replace('btn-primary', 'btn-outline-primary'));
            this.classList.replace('btn-outline-primary', 'btn-primary');

            const configId = String(this.dataset.id);
            const configData = allConfigs[configId];

            if (configData) {
                activeProblems = configData.problems;
                currentConfigId = configId;
                elements.modeLabel.innerText = configData.label;
                elements.modeInfo.classList.remove('d-none');
            }
        });
    });

    // СТАРТ
    document.getElementById('startWorkoutBtn').addEventListener('click', () => {
        if (activeProblems.length === 0) return;
        elements.setupScreen.classList.add('d-none');
        elements.workoutScreen.classList.remove('d-none');
        startTime = new Date();
        startTimer();
        loadQuestion();
    });

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
        if (!elements.input.value) return;
        results.push({
            q: activeProblems[currentIdx].question,
            user_a: elements.input.value,
            correct_a: activeProblems[currentIdx].answer,
            is_correct: elements.input.value === activeProblems[currentIdx].answer
        });
        currentIdx++;
        loadQuestion();
    }

    function startTimer() {
        timerInterval = setInterval(() => {
            let diff = Math.floor((new Date() - startTime) / 1000);
            let m = Math.floor(diff / 60).toString().padStart(2, '0');
            let s = (diff % 60).toString().padStart(2, '0');
            elements.timer.innerText = `${m}:${s}`;
        }, 1000);
    }

    // Слушатели событий
    elements.nextBtn.addEventListener('click', handleNext);
    elements.input.addEventListener('keypress', (e) => { if(e.key === 'Enter') handleNext(); });
    elements.finishBtn.addEventListener('click', () => finishTraining());

    async function finishTraining() {
        clearInterval(timerInterval);

        // 1. Объявляем переменные ОДИН раз в начале функции
        const total = results.length;
        const correctCount = results.filter(r => r.is_correct).length;
        const timeStr = document.getElementById('timer').innerText;
        const percent = total > 0 ? Math.round((correctCount / total) * 100) : 0;

        // 2. Обновляем модалку (теперь используем наши переменные)
        document.getElementById('resSolved').innerText = total;
        document.getElementById('resCorrectCount').innerText = correctCount;
        document.getElementById('resCorrectPercent').innerText = percent + '%';
        document.getElementById('resTime').innerText = timeStr;

        // Показываем модалку
        const modal = new bootstrap.Modal(document.getElementById('resultModal'));
        modal.show();


        document.getElementById('showDetailsBtn').addEventListener('click', function() {
        const tableBody = document.getElementById('detailsTableBody');
        tableBody.innerHTML = ''; // Очищаем старые данные

        results.forEach(res => {
            const row = `
                <tr>
                    <td>${res.q}</td>
                    <td class="${res.is_correct ? 'text-success' : 'text-danger fw-bold'}">${res.user_a}</td>
                    <td><span class="badge bg-secondary">${res.correct_a}</span></td>
                    <td>${res.is_correct ? '✅' : '❌'}</td>
                </tr>
            `;
            tableBody.insertAdjacentHTML('beforeend', row);
        });

        document.getElementById('detailedResults').classList.remove('d-none');
        this.classList.add('d-none'); // Прячем саму кнопку "Подробнее"
    });

        // 2. А сохраняем ТОЛЬКО если пользователь залогинен
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
                    total: total,
                    correct: correctCount,
                    details: results
                })
            });

            if (!response.ok) throw new Error("Ошибка сервера");
            console.log("Результат сохранен в профиль.");
        } catch (error) {
            console.error("Ошибка сохранения:", error);
            alert("Не удалось сохранить результат в ваш профиль.");
        }
        } else {
            console.log("Режим гостя: результат не будет сохранен в базу.");
        }
    }
});