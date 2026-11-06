window.PickerUI = (function () {
    let uid = 0;

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text) e.textContent = text;
        return e;
    }

    function radios(name, options, current, onPick, asButtons) {
        const wrap = el('div', asButtons ? 'd-flex flex-wrap gap-2' : 'd-grid gap-1');
        options.forEach((o, i) => {
            const id = `${name}-${i}`;
            const input = el('input', asButtons ? 'btn-check' : 'form-check-input me-2');
            input.type = 'radio'; input.name = name; input.id = id; input.value = o.value;
            input.checked = o.value === current;
            input.addEventListener('change', () => onPick(o.value));
            const label = el('label', asButtons ? 'btn btn-outline-primary' : 'form-check-label', o.label);
            label.htmlFor = id;
            if (asButtons) {
                wrap.append(input, label);
            } else {
                const row = el('div', 'form-check');
                row.append(input, label);
                wrap.append(row);
            }
        });
        return wrap;
    }

    function render(box, picker, initial, onChange, isLocked = false) {
        box.innerHTML = '';
        initial = initial || {};
        const ns = 'pk' + (++uid);
        const selection = {};
        const values = picker.options.map(o => o.value);

        // Строгая валидация: для single требуется выбранное значение из списка, для multi — хотя бы один элемент
        const valid = () => {
            if (picker.mode === 'single') {
                return values.includes(String(selection[picker.key]));
            }
            return (selection[picker.key] || []).length > 0;
        };

        const emit = () => onChange && onChange(selection, valid());
        let levelBox = null;

        box.append(el('div', 'fw-bold mb-2', picker.title));

        if (picker.mode === 'single') {
            const cur = values.includes(String(initial[picker.key])) ? String(initial[picker.key]) : (isLocked ? picker.default : '');
            selection[picker.key] = cur;
            const radioWrap = radios(`${ns}-${picker.key}`, picker.options, cur,
                v => { selection[picker.key] = v; emit(); }, true);
            if (isLocked) {
                radioWrap.querySelectorAll('input').forEach(inp => inp.disabled = true);
            }
            box.append(radioWrap);
        } else {
            const init = Array.isArray(initial[picker.key])
                ? initial[picker.key].filter(v => values.includes(v))
                : (isLocked ? [...picker.default] : []);

            selection[picker.key] = init;

            const list = el('div', 'd-grid gap-1');
            picker.options.forEach((o, i) => {
                const id = `${ns}-op-${i}`;
                const row = el('div', 'form-check p-2 ps-5 border rounded bg-white');
                const input = el('input', 'form-check-input');
                input.type = 'checkbox'; input.id = id; input.value = o.value;
                input.checked = selection[picker.key].includes(o.value);

                if (isLocked) {
                    input.disabled = true;
                }

                input.addEventListener('change', () => {
                    const set = new Set(selection[picker.key]);
                    input.checked ? set.add(o.value) : set.delete(o.value);
                    selection[picker.key] = [...set];
                    if (levelBox) levelBox.classList.toggle('d-none', !set.has(picker.level.shown_when));
                    emit();
                });
                const label = el('label', 'form-check-label w-100', o.label);
                label.htmlFor = id;
                row.append(input, label);
                list.append(row);
            });
            box.append(list);

            if (picker.level) {
                const lvValues = picker.level.options.map(o => o.value);
                const lv = lvValues.includes(initial[picker.level.key]) ? initial[picker.level.key] : picker.level.default;
                selection[picker.level.key] = lv;
                levelBox = el('div', 'mt-3 p-3 border rounded bg-white' +
                    (selection[picker.key].includes(picker.level.shown_when) ? '' : ' d-none'));
                levelBox.append(el('div', 'fw-bold small mb-2', picker.level.title));

                const levelRadios = radios(`${ns}-${picker.level.key}`, picker.level.options, lv,
                    v => { selection[picker.level.key] = v; emit(); }, false);
                if (isLocked) {
                    levelRadios.querySelectorAll('input').forEach(inp => inp.disabled = true);
                }
                levelBox.append(levelRadios);
                box.append(levelBox);
            }
        }
        emit();
        return { selection, isValid: valid };
    }

    return { render };
})();