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

    function recalc(row) {
        const quantity = n(row.querySelector('[name="quantity"]')?.value);
        const rate = n(row.querySelector('[name="rate"]')?.value);
        const discountPercent = n(row.querySelector('[name="discount_percent"]')?.value);
        const discountAmountInput = n(row.querySelector('[name="discount_amount"]')?.value);
        const taxPercent = n(row.querySelector('[name="tax_percent"]')?.value);
        const base = quantity * rate;
        const discount = discountAmountInput > 0 ? discountAmountInput : base * discountPercent / 100;
        const taxable = Math.max(0, base - discount);
        const tax = taxable * taxPercent / 100;
        const total = taxable + tax;
        const totalInput = row.querySelector(".sr-line-total");
        if (totalInput) totalInput.value = money(total);
    }

    function rowHtml(item, taxEnabled) {
        return `
            <tr>
                <td>
                    <input type="hidden" name="item_service_id" value="${esc(item.item_service_id)}">
                    <input type="hidden" name="sales_invoice_item_id" value="${esc(item.sales_invoice_item_id)}">
                    <input class="form-control" name="description" value="${esc(item.description)}" readonly>
                </td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0.01" max="${esc(item.max_quantity || item.quantity)}" name="quantity" value="${esc(item.quantity || "0")}"></td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0" name="rate" value="${esc(item.rate || "0")}" readonly></td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0" max="100" name="discount_percent" value="${esc(item.discount_percent || "0")}" readonly></td>
                <td><input class="form-control sr-calc" type="number" step="0.01" min="0" name="discount_amount" value="${esc(item.discount_amount || "0")}" readonly></td>
                ${taxEnabled ? `<td><input class="form-control sr-calc" type="number" step="0.01" min="0" max="100" name="tax_percent" value="${esc(item.tax_percent || "0")}" readonly></td>` : `<input type="hidden" name="tax_percent" value="0">`}
                <td><input class="form-control sr-line-total" readonly value="0.00"></td>
            </tr>
        `;
    }

    async function loadInvoiceItems(form, invoiceId) {
        const tableBody = document.querySelector("#sales-return-items tbody");
        if (!tableBody) return;
        tableBody.innerHTML = "";
        if (!invoiceId) return;
        const template = form.dataset.itemsUrlTemplate;
        const response = await fetch(template.replace("/0/", `/${invoiceId}/`), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch invoice items.");
        const customerSelect = form.querySelector('[name="customer_id"]');
        if (customerSelect && payload.customer_id) customerSelect.value = payload.customer_id;
        const taxEnabled = document.querySelector('#sales-return-items thead th:nth-last-child(2)')?.textContent.trim() === "Tax %";
        tableBody.innerHTML = (payload.items || []).map((item) => rowHtml(item, taxEnabled)).join("");
        tableBody.querySelectorAll("tr").forEach(recalc);
    }

    document.addEventListener("input", (event) => {
        if (event.target.classList.contains("sr-calc")) recalc(event.target.closest("tr"));
    });

    document.addEventListener("change", async (event) => {
        if (event.target.name !== "sales_invoice_id") return;
        const form = event.target.closest("form");
        if (!form?.dataset.itemsUrlTemplate) return;
        try {
            await loadInvoiceItems(form, event.target.value);
        } catch (error) {
            alert(error.message || "Unable to fetch invoice items.");
        }
    });

    document.querySelectorAll("#sales-return-items tbody tr").forEach(recalc);
})();
