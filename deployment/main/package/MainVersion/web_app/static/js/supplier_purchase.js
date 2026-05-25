document.addEventListener("DOMContentLoaded", () => {
    const body = document.querySelector("#purchaseItemsBody");
    const addButton = document.querySelector("#addPurchaseRow");
    const template = document.querySelector("#purchaseRowTemplate");
    if (!body || !template) return;

    const numberValue = (input) => {
        const value = Number.parseFloat(input?.value || "0");
        return Number.isFinite(value) ? value : 0;
    };
    const money = (value) => (Math.round(value * 100) / 100).toFixed(2);

    const recalcRow = (row) => {
        const quantity = numberValue(row.querySelector("[name='quantity[]']"));
        const rate = numberValue(row.querySelector("[name='purchase_rate[]']"));
        const taxPercent = numberValue(row.querySelector("[name='tax_percent[]']"));
        const taxAmountInput = row.querySelector("[name='tax_amount_display[]']");
        const lineTotalInput = row.querySelector("[name='line_total_display[]']");
        const base = quantity * rate;
        const tax = base * taxPercent / 100;
        const total = base + tax;
        if (taxAmountInput) taxAmountInput.value = money(tax);
        if (lineTotalInput) lineTotalInput.value = money(total);
        return { base, tax, total };
    };

    const recalcTotals = () => {
        let subtotal = 0;
        let tax = 0;
        let grand = 0;
        body.querySelectorAll(".purchase-item-row").forEach((row) => {
            const line = recalcRow(row);
            subtotal += line.base;
            tax += line.tax;
            grand += line.total;
        });
        const subtotalDisplay = document.querySelector("#subtotalDisplay");
        const taxDisplay = document.querySelector("#taxDisplay");
        const grandDisplay = document.querySelector("#grandDisplay");
        if (subtotalDisplay) subtotalDisplay.textContent = money(subtotal);
        if (taxDisplay) taxDisplay.textContent = money(tax);
        if (grandDisplay) grandDisplay.textContent = money(grand);
    };

    const bindRow = (row) => {
        row.querySelectorAll(".calc-field").forEach((input) => input.addEventListener("input", recalcTotals));
        row.querySelector(".remove-row")?.addEventListener("click", () => {
            if (body.querySelectorAll(".purchase-item-row").length > 1) {
                row.remove();
                recalcTotals();
            }
        });
        row.querySelector(".item-select")?.addEventListener("change", (event) => {
            const option = event.target.selectedOptions[0];
            if (!option) return;
            const description = row.querySelector("[name='description[]']");
            const rate = row.querySelector("[name='purchase_rate[]']");
            const tax = row.querySelector("[name='tax_percent[]']");
            if (option.dataset.description && !description.value.trim()) description.value = option.dataset.description;
            if (option.dataset.rate) rate.value = money(Number.parseFloat(option.dataset.rate || "0"));
            if (tax && option.dataset.tax) tax.value = money(Number.parseFloat(option.dataset.tax || "0"));
            recalcTotals();
        });
    };

    addButton?.addEventListener("click", () => {
        const clone = template.content.firstElementChild.cloneNode(true);
        body.appendChild(clone);
        bindRow(clone);
        recalcTotals();
    });

    body.querySelectorAll(".purchase-item-row").forEach(bindRow);
    recalcTotals();
});
