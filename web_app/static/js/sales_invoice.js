document.addEventListener("DOMContentLoaded", () => {
    const body = document.querySelector("#invoiceItemsBody");
    const addButton = document.querySelector("#addInvoiceRow");
    const template = document.querySelector("#invoiceRowTemplate");
    if (!body || !template) return;
    const num = (el) => { const value = Number.parseFloat(el?.value || "0"); return Number.isFinite(value) ? value : 0; };
    const money = (value) => (Math.round(value * 100) / 100).toFixed(2);
    const recalcRow = (row) => {
        const qty = num(row.querySelector("[name='quantity[]']"));
        const rate = num(row.querySelector("[name='rate[]']"));
        const discPctEl = row.querySelector("[name='discount_percent[]']");
        const discAmtEl = row.querySelector("[name='discount_amount[]']");
        const taxPct = num(row.querySelector("[name='tax_percent[]']"));
        const base = qty * rate;
        let discount = num(discAmtEl);
        if (num(discPctEl) > 0) {
            discount = base * num(discPctEl) / 100;
            discAmtEl.value = money(discount);
        }
        discount = Math.min(discount, base);
        const taxable = Math.max(0, base - discount);
        const tax = taxable * taxPct / 100;
        const total = taxable + tax;
        row.querySelector("[name='tax_amount_display[]']").value = money(tax);
        row.querySelector("[name='line_total_display[]']").value = money(total);
        return { base, discount, tax, total };
    };
    const recalcTotals = () => {
        let subtotal = 0, discount = 0, tax = 0, grand = 0;
        body.querySelectorAll(".invoice-item-row").forEach((row) => {
            const line = recalcRow(row);
            subtotal += line.base; discount += line.discount; tax += line.tax; grand += line.total;
        });
        document.querySelector("#subtotalDisplay").textContent = money(subtotal);
        document.querySelector("#discountDisplay").textContent = money(discount);
        document.querySelector("#taxDisplay").textContent = money(tax);
        document.querySelector("#grandDisplay").textContent = money(grand);
    };
    const bindRow = (row) => {
        row.querySelectorAll(".calc-field").forEach((input) => input.addEventListener("input", recalcTotals));
        row.querySelector(".remove-row")?.addEventListener("click", () => {
            if (body.querySelectorAll(".invoice-item-row").length > 1) {
                row.remove(); recalcTotals();
            }
        });
        row.querySelector(".item-select")?.addEventListener("change", (event) => {
            const option = event.target.selectedOptions[0];
            if (!option) return;
            const desc = row.querySelector("[name='description[]']");
            if (option.dataset.description && !desc.value.trim()) desc.value = option.dataset.description;
            row.querySelector("[name='rate[]']").value = money(Number.parseFloat(option.dataset.rate || "0"));
            row.querySelector("[name='tax_percent[]']").value = money(Number.parseFloat(option.dataset.tax || "0"));
            recalcTotals();
        });
    };
    addButton?.addEventListener("click", () => { const clone = template.content.firstElementChild.cloneNode(true); body.appendChild(clone); bindRow(clone); recalcTotals(); });
    body.querySelectorAll(".invoice-item-row").forEach(bindRow);
    recalcTotals();
});
