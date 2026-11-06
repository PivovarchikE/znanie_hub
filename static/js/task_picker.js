(function () {
    const dataEl = document.getElementById('all-configs-data');
    const box = document.getElementById('pickerBox');
    const startBtn = document.getElementById('startWorkoutBtn');
    const modeLabel = document.getElementById('currentModeLabel');
    if (!dataEl || !box || !startBtn || !window.PickerUI) return;

    const configs = JSON.parse(dataEl.textContent);
    const API = box.dataset.api;
    let currentId = null;
    let selection = {};
    let pickerValid = false;

    const activePicker = () => (currentId && configs[currentId]) ? configs[currentId].picker : null;

    function updateStartState() {
        const picker = activePicker();
        // Если есть пикер — ждем выбора пользователя (pickerValid), иначе проверяем наличие выбранной кнопки (currentId)
        startBtn.disabled = picker ? !pickerValid : !currentId;
    }

    function render() {
        box.innerHTML = '';
        const picker = activePicker();

        if (modeLabel) {
            modeLabel.innerText = (currentId && configs[currentId]) ? configs[currentId].label : 'Не выбран';
        }

        if (!picker) {
            selection = {};
            pickerValid = true;
            updateStartState();
            return;
        }

        const isLocked = Boolean(CONFIG_DATA.presetConfigId);
        const initialSettings = CONFIG_DATA.presetSettings || null;

        PickerUI.render(box, picker, initialSettings, (sel, ok) => {
            selection = sel;
            pickerValid = ok;
            updateStartState();
        }, isLocked);
    }

    // Обработка кликов по кнопкам тренажеров (для сложения и вычитания)
    document.querySelectorAll('.config-select-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled) return;
            // Убираем подсветку со всех кнопок и ставим на текущую
            document.querySelectorAll('.config-select-btn').forEach(b => b.classList.remove('btn-primary', 'shadow-sm'));
            document.querySelectorAll('.config-select-btn').forEach(b => b.classList.add('btn-outline-primary'));
            btn.classList.remove('btn-outline-primary');
            btn.classList.add('btn-primary', 'shadow-sm');

            currentId = btn.dataset.id;
            render();
        });
    });

    // --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ СТРАНИЦЫ ---
    if (typeof CONFIG_DATA !== 'undefined' && CONFIG_DATA.presetConfigId) {
        // Если ДЗ назначено учителем — берем фиксированный конфиг
        currentId = String(CONFIG_DATA.presetConfigId);
        render();
    } else {
        // Проверяем, есть ли на странице конфиг с пикером (Таблица умножения / Умножение и деление)
        const pickerConfigId = Object.keys(configs).find(id => configs[id].picker);

        if (pickerConfigId) {
            // Если это тренажер с пикером — сразу активируем его, чтобы настройки отобразились
            currentId = pickerConfigId;
            render();
        } else {
            // Если это обычный тренажер (Сложение и вычитание) — НИЧЕГО не выбираем по умолчанию!
            currentId = null;
            updateStartState();
        }
    }

    window.TaskPicker = {
        async fetchProblems(configId) {
            const picker = activePicker();
            if (!picker || String(configId) !== String(currentId)) return null;
            try {
                const qs = new URLSearchParams({ config_id: currentId });
                Object.entries(selection).forEach(([k, v]) =>
                    qs.set(k, Array.isArray(v) ? v.join(',') : v));
                const res = await fetch(`${API}?${qs}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (!res.ok) throw new Error('bad status');
                const { problems } = await res.json();
                if (!problems || !problems.length) throw new Error('empty');
                return problems;
            } catch (err) {
                alert('Не удалось получить задания. Попробуйте еще раз.');
                return null;
            }
        }
    };
})();