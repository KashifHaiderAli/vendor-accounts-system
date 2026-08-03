document.addEventListener("DOMContentLoaded", () => {
    console.log("quotation.js loaded: qtax_discount_fix_20260520");

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
    const form = document.querySelector("#quotationForm");

    if (!body || !template) return;

    const numberValue = (input) => {
        const value = Number.parseFloat(input?.value || "0");
        return Number.isFinite(value) ? value : 0;
    };

    const roundMoney = (value) => Math.round((Number(value) || 0) * 100) / 100;
    const money = (value) => roundMoney(value).toFixed(2);
    const quantityText = (value) => {
        const rounded = roundMoney(value);
        return Number.isInteger(rounded) ? String(rounded) : String(rounded).replace(/0+$/, "").replace(/\.$/, "");
    };

    function calculateLine(quantity, rate, discountPercent, discountAmount, taxPercent, option) {
        const base = quantity * rate;
        let discount = discountPercent > 0 ? base * discountPercent / 100 : discountAmount;
        discount = Math.min(Math.max(discount, 0), base);
        const discounted = Math.max(0, base - discount);

        let tax = 0;
        let lineTotal = discounted;

        if (option === "tax_exclusive") {
            tax = discounted * taxPercent / 100;
            lineTotal = discounted + tax;
        } else if (option === "tax_inclusive" && taxPercent > 0) {
            tax = discounted * taxPercent / (100 + taxPercent);
            lineTotal = discounted;
        } else {
            tax = 0;
            lineTotal = discounted;
        }

        return { base, discount, discounted, tax, lineTotal };
    }

    const recalcRow = (row) => {
        const quantity = numberValue(row.querySelector("[name='quantity[]']"));
        const rate = numberValue(row.querySelector("[name='rate[]']"));
        const discountPercentInput = row.querySelector("[name='discount_percent[]']");
        const discountAmountInput = row.querySelector("[name='discount_amount[]']");
        const taxPercentInput = row.querySelector("[name='tax_percent[]']");
        const taxAmountInput = row.querySelector("[name='tax_amount_display[]']");
        const lineTotalInput = row.querySelector("[name='line_total_display[]']");

        const discountPercent = numberValue(discountPercentInput);
        const discountAmount = numberValue(discountAmountInput);
        const taxPercent = taxOption?.value === "no_tax" ? 0 : numberValue(taxPercentInput);
        const line = calculateLine(quantity, rate, discountPercent, discountAmount, taxPercent, taxOption?.value || "tax_exclusive");

        if (discountPercent > 0 || discountAmount > line.base) {
            discountAmountInput.value = money(line.discount);
        }
        if (taxAmountInput) taxAmountInput.value = money(line.tax);
        lineTotalInput.value = money(line.lineTotal);
        const quantityDisplay = row.querySelector("[data-quantity-display]");
        if (quantityDisplay) quantityDisplay.textContent = quantityText(quantity);
        console.log("Quotation line calc", line);
        return line;
    };

    const recalcTotals = () => {
        let subtotal = 0;
        let discount = 0;
        let tax = 0;
        let grand = 0;
        body.querySelectorAll(".quotation-item-row").forEach((row) => {
            const line = recalcRow(row);
            subtotal += line.base;
            discount += line.discount;
            tax += line.tax;
            grand += line.lineTotal;
        });
        document.querySelector("#subtotalDisplay").textContent = money(subtotal);
        document.querySelector("#discountDisplay").textContent = money(discount);
        const taxDisplay = document.querySelector("#taxDisplay");
        if (taxDisplay) taxDisplay.textContent = money(tax);
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
            if (tax && option.value) {
                tax.value = money(Number.parseFloat(option.dataset.tax || "0"));
            }
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
    form?.addEventListener("submit", (event) => {
        const customerFlag = form.querySelector("[name='auto_create_customer_confirmed']");
        const itemFlag = form.querySelector("[name='auto_create_items_confirmed']");
        const hasNewCustomer = customerMode?.value === "new" && Boolean(document.querySelector("#customerName")?.value.trim());
        const hasManualItems = Array.from(body.querySelectorAll(".quotation-item-row")).some((row) => {
            const itemId = row.querySelector("[name='item_service_id[]']")?.value || "";
            const description = row.querySelector("[name='description[]']")?.value.trim() || "";
            return !itemId && description;
        });
        if (hasNewCustomer && customerFlag?.value !== "1") {
            if (!window.confirm("This customer is not available in Customer Master. Do you want to add it as a new customer?")) {
                event.preventDefault();
                document.querySelector("#customerName")?.focus();
                return;
            }
            customerFlag.value = "1";
        }
        if (hasManualItems && itemFlag?.value !== "1") {
            if (!window.confirm("One or more items are not available in Item Master. Do you want to add them as new items?")) {
                event.preventDefault();
                return;
            }
            itemFlag.value = "1";
        }
    });
    recalcTotals();
});
