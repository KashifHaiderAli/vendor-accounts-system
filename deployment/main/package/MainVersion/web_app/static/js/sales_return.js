(function () {
    function n(value) {
        return Number(value || 0) || 0;
    }

    function money(value) {
        return n(value).toFixed(2);
    }

    function esc(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function urlFromTemplate(template, id) {
        return String(template || "").replace("/0/", `/${id}/`);
    }

    function taxEnabled() {
        return Array.from(document.querySelectorAll("#sales-return-items thead th"))
            .some((th) => th.textContent.trim() === "Tax %");
    }

    function calculateLine(row) {
        const quantityInput = row.querySelector('[name="quantity"]');
        const maxQty = n(quantityInput?.getAttribute("max"));
        let quantity = n(quantityInput?.value);
        if (maxQty > 0 && quantity > maxQty) {
            quantity = maxQty;
            quantityInput.value = money(maxQty);
        }
        const rate = n(row.querySelector('[name="rate"]')?.value);
        const discountPercent = n(row.querySelector('[name="discount_percent"]')?.value);
        const discountAmountInput = n(row.querySelector('[name="discount_amount"]')?.value);
        const taxPercent = n(row.querySelector('[name="tax_percent"]')?.value);
        const base = quantity * rate;
        const discount = discountAmountInput > 0 ? Math.min(discountAmountInput, base) : base * discountPercent / 100;
        const taxable = Math.max(0, base - discount);
        const tax = taxable * taxPercent / 100;
        const total = taxable + tax;
        const totalInput = row.querySelector(".sr-line-total");
        if (totalInput) totalInput.value = money(total);
        return total;
    }

    function recalcAll() {
        let total = 0;
        document.querySelectorAll("#sales-return-items tbody tr").forEach((row) => {
            total += calculateLine(row);
        });
        const display = document.querySelector("#sales-return-total");
        if (display) display.textContent = money(total);
    }

    function rowHtml(item) {
        const maxQty = item.max_returnable_qty || item.max_quantity || item.quantity || "0";
        return `
            <tr>
                <td>
                    <input type="hidden" name="item_service_id" value="${esc(item.item_id || item.item_service_id)}">
                    <input type="hidden" name="sales_invoice_item_id" value="${esc(item.invoice_item_id || item.sales_invoice_item_id)}">
                    <input type="hidden" name="discount_percent" value="${esc(item.discount_percent || "0")}">
                    <input type="hidden" name="discount_amount" value="${esc(item.discount_amount || "0")}">
                    <input class="form-control" name="description" value="${esc(item.description || item.item_name)}" readonly>
                </td>
                <td><input class="form-control" value="${esc(item.invoiced_qty || item.quantity || "0")}" readonly></td>
                <td><input class="form-control" value="${esc(item.already_returned_qty || "0")}" readonly></td>
                <td><input class="form-control" value="${esc(maxQty)}" readonly></td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0.01" max="${esc(maxQty)}" name="quantity" value="${esc(maxQty)}"></td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0" name="rate" value="${esc(item.rate || "0")}" readonly></td>
                ${taxEnabled() ? `<td><input class="form-control sr-calc" type="number" step="0.01" min="0" max="100" name="tax_percent" value="${esc(item.tax_percent || "0")}" readonly></td>` : `<input type="hidden" name="tax_percent" value="0">`}
                <td><input class="form-control sr-line-total" readonly value="${esc(item.line_total || "0.00")}"></td>
                <td class="text-end"><button class="btn btn-sm btn-outline-danger sr-remove-row" type="button">X</button></td>
            </tr>
        `;
    }

    function populateInvoices(select, invoices) {
        const current = select.value;
        select.innerHTML = `<option value="">Select</option>` + (invoices || []).map((invoice) => {
            const selected = String(invoice.id) === String(current) ? " selected" : "";
            return `<option value="${esc(invoice.id)}" data-customer-id="${esc(invoice.customer_id)}"${selected}>${esc(invoice.invoice_no)}</option>`;
        }).join("");
    }

    async function loadCustomerInvoices(form, customerId) {
        const invoiceSelect = form.querySelector('[name="sales_invoice_id"]');
        if (!invoiceSelect || !form.dataset.invoicesUrlTemplate) return;
        if (!customerId) return;
        const response = await fetch(urlFromTemplate(form.dataset.invoicesUrlTemplate, customerId), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch customer invoices.");
        populateInvoices(invoiceSelect, payload.invoices || []);
    }

    async function loadInvoiceItems(form, invoiceId) {
        const tableBody = document.querySelector("#sales-return-items tbody");
        if (!tableBody) return;
        tableBody.innerHTML = "";
        if (!invoiceId) {
            recalcAll();
            return;
        }
        const response = await fetch(urlFromTemplate(form.dataset.itemsUrlTemplate, invoiceId), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch invoice items.");
        const customerSelect = form.querySelector('[name="customer_id"]');
        if (customerSelect && payload.customer_id) customerSelect.value = payload.customer_id;
        tableBody.innerHTML = (payload.items || []).map(rowHtml).join("");
        recalcAll();
    }

    document.addEventListener("input", (event) => {
        if (event.target.classList.contains("sr-calc")) recalcAll();
    });

    document.addEventListener("click", (event) => {
        const button = event.target.closest(".sr-remove-row");
        if (!button) return;
        button.closest("tr")?.remove();
        recalcAll();
    });

    document.addEventListener("change", async (event) => {
        const form = event.target.closest("form");
        if (!form) return;
        try {
            if (event.target.name === "customer_id") {
                await loadCustomerInvoices(form, event.target.value);
                document.querySelector("#sales-return-items tbody").innerHTML = "";
                recalcAll();
            }
            if (event.target.name === "sales_invoice_id") {
                await loadInvoiceItems(form, event.target.value);
            }
        } catch (error) {
            alert(error.message || "Unable to update sales return items.");
        }
    });

    recalcAll();
})();
