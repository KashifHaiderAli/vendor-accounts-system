document.addEventListener("DOMContentLoaded", () => {
    const body = document.querySelector("#quotationItemsBody");
    const addButton = document.querySelector("#addQuotationRow");
    const template = document.querySelector("#quotationRowTemplate");
    const taxOption = document.querySelector("#taxOption");
    const customerMode = document.querySelector("#customerMode");
    const customerSelect = document.querySelector("#customerSelect");
    const contactPerson = document.querySelector("#contactPerson");
    const paymentTerms = document.querySelector("#paymentTerms");
    const quotationDate = document.querySelector("input[name='quotation_date']");
    const validityDays = document.querySelector("#validityDays");
    const validTill = document.querySelector("input[name='valid_till']");

    if (!body || !template) return;

    const numberValue = (input) => {
        const value = Number.parseFloat(input?.value || "0");
        return Number.isFinite(value) ? value : 0;
    };

    const money = (value) => (Math.round(value * 100) / 100).toFixed(2);

    const recalcRow = (row) => {
        const quantity = numberValue(row.querySelector("[name='quantity[]']"));
        const rate = numberValue(row.querySelector("[name='rate[]']"));
        const discountPercentInput = row.querySelector("[name='discount_percent[]']");
        const discountAmountInput = row.querySelector("[name='discount_amount[]']");
        const taxPercentInput = row.querySelector("[name='tax_percent[]']");
        const taxAmountInput = row.querySelector("[name='tax_amount_display[]']");
        const lineTotalInput = row.querySelector("[name='line_total_display[]']");

        const gross = quantity * rate;
        const discountPercent = numberValue(discountPercentInput);
        let discountAmount = numberValue(discountAmountInput);
        if (discountPercent > 0) {
            discountAmount = gross * discountPercent / 100;
            discountAmountInput.value = money(discountAmount);
        }
        discountAmount = Math.min(discountAmount, gross);
        let net = Math.max(0, gross - discountAmount);
        let taxPercent = taxOption?.value === "no_tax" ? 0 : numberValue(taxPercentInput);
        let taxAmount = 0;
        let lineTotal = net;

        if (taxOption?.value === "tax_exclusive") {
            taxAmount = net * taxPercent / 100;
            lineTotal = net + taxAmount;
        } else if (taxOption?.value === "tax_inclusive" && taxPercent > 0) {
            taxAmount = net * taxPercent / (100 + taxPercent);
            lineTotal = net;
        }

        if (taxOption?.value === "no_tax") {
            taxPercentInput.value = "0.00";
        }
        taxAmountInput.value = money(taxAmount);
        lineTotalInput.value = money(lineTotal);
        return { gross, discountAmount, taxAmount, lineTotal };
    };

    const recalcTotals = () => {
        let subtotal = 0;
        let discount = 0;
        let tax = 0;
        let grand = 0;
        body.querySelectorAll(".quotation-item-row").forEach((row) => {
            const line = recalcRow(row);
            subtotal += line.gross;
            discount += line.discountAmount;
            tax += line.taxAmount;
            grand += line.lineTotal;
        });
        document.querySelector("#subtotalDisplay").textContent = money(subtotal);
        document.querySelector("#discountDisplay").textContent = money(discount);
        document.querySelector("#taxDisplay").textContent = money(tax);
        document.querySelector("#grandDisplay").textContent = money(grand);
    };

    const bindRow = (row) => {
        row.querySelectorAll(".calc-field").forEach((input) => input.addEventListener("input", recalcTotals));
        row.querySelector(".remove-row")?.addEventListener("click", () => {
            if (body.querySelectorAll(".quotation-item-row").length > 1) {
                row.remove();
                recalcTotals();
            }
        });
        row.querySelector(".item-select")?.addEventListener("change", (event) => {
            const option = event.target.selectedOptions[0];
            if (!option) return;
            const description = row.querySelector("[name='description[]']");
            const rate = row.querySelector("[name='rate[]']");
            const tax = row.querySelector("[name='tax_percent[]']");
            if (option.dataset.description && !description.value.trim()) {
                description.value = option.dataset.description;
            }
            if (option.dataset.rate) rate.value = money(Number.parseFloat(option.dataset.rate || "0"));
            if (option.dataset.tax && taxOption?.value !== "no_tax") tax.value = money(Number.parseFloat(option.dataset.tax || "0"));
            recalcTotals();
        });
    };

    addButton?.addEventListener("click", () => {
        const clone = template.content.firstElementChild.cloneNode(true);
        body.appendChild(clone);
        bindRow(clone);
        recalcTotals();
    });

    taxOption?.addEventListener("change", recalcTotals);
    body.querySelectorAll(".quotation-item-row").forEach(bindRow);

    customerSelect?.addEventListener("change", () => {
        const option = customerSelect.selectedOptions[0];
        if (!option) return;
        if (contactPerson && option.dataset.contact && !contactPerson.value.trim()) {
            contactPerson.value = option.dataset.contact;
        }
        if (paymentTerms && option.dataset.terms) {
            paymentTerms.value = option.dataset.terms;
        }
    });

    const syncCustomerMode = () => {
        const isNew = customerMode?.value === "new";
        document.querySelectorAll(".customer-existing-field").forEach((field) => {
            field.style.display = isNew ? "none" : "";
        });
        document.querySelectorAll(".customer-new-field").forEach((field) => {
            field.style.display = isNew ? "" : "none";
        });
    };
    customerMode?.addEventListener("change", syncCustomerMode);
    syncCustomerMode();

    const updateValidTill = () => {
        if (!quotationDate?.value || !validityDays || !validTill) return;
        const days = Number.parseInt(validityDays.value || "0", 10);
        const start = new Date(`${quotationDate.value}T00:00:00`);
        if (!Number.isFinite(days) || Number.isNaN(start.getTime())) return;
        start.setDate(start.getDate() + days);
        validTill.value = start.toISOString().slice(0, 10);
    };
    quotationDate?.addEventListener("change", updateValidTill);
    validityDays?.addEventListener("input", updateValidTill);
    recalcTotals();
});
