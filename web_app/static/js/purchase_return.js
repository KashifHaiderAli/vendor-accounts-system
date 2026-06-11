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
        const rate = n(row.querySelector('[name="purchase_rate"]')?.value);
        const taxPercent = n(row.querySelector('[name="tax_percent"]')?.value);
        const base = quantity * rate;
        const tax = base * taxPercent / 100;
        const totalInput = row.querySelector(".pr-line-total");
        if (totalInput) totalInput.value = money(base + tax);
    }

    function rowHtml(item, taxEnabled) {
        return `
            <tr>
                <td>
                    <input type="hidden" name="item_service_id" value="${esc(item.item_service_id)}">
                    <input type="hidden" name="supplier_purchase_item_id" value="${esc(item.supplier_purchase_item_id)}">
                    <input class="form-control" name="description" value="${esc(item.description)}" readonly>
                </td>
                <td><input class="form-control pr-calc" type="number" step="0.01" min="0.01" max="${esc(item.max_quantity || item.quantity)}" name="quantity" value="${esc(item.quantity || "0")}"></td>
                <td><input class="form-control pr-calc" type="number" step="0.01" min="0" name="purchase_rate" value="${esc(item.purchase_rate || "0")}" readonly></td>
                ${taxEnabled ? `<td><input class="form-control pr-calc" type="number" step="0.01" min="0" max="100" name="tax_percent" value="${esc(item.tax_percent || "0")}" readonly></td>` : `<input type="hidden" name="tax_percent" value="0">`}
                <td><input class="form-control pr-line-total" readonly value="0.00"></td>
            </tr>
        `;
    }

    async function loadPurchaseItems(form, purchaseId) {
        const tableBody = document.querySelector("#purchase-return-items tbody");
        if (!tableBody) return;
        tableBody.innerHTML = "";
        if (!purchaseId) return;
        const template = form.dataset.itemsUrlTemplate;
        const response = await fetch(template.replace("/0/", `/${purchaseId}/`), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch purchase items.");
        const supplierSelect = form.querySelector('[name="supplier_id"]');
        if (supplierSelect && payload.supplier_id) supplierSelect.value = payload.supplier_id;
        const billInput = form.querySelector('[name="supplier_bill_no"]');
        if (billInput && payload.supplier_bill_no) billInput.value = payload.supplier_bill_no;
        const taxEnabled = document.querySelector('#purchase-return-items thead th:nth-last-child(2)')?.textContent.trim() === "Tax %";
        tableBody.innerHTML = (payload.items || []).map((item) => rowHtml(item, taxEnabled)).join("");
        tableBody.querySelectorAll("tr").forEach(recalc);
    }

    document.addEventListener("input", (event) => {
        if (event.target.classList.contains("pr-calc")) recalc(event.target.closest("tr"));
    });

    document.addEventListener("change", async (event) => {
        if (event.target.name !== "supplier_purchase_id") return;
        const form = event.target.closest("form");
        if (!form?.dataset.itemsUrlTemplate) return;
        try {
            await loadPurchaseItems(form, event.target.value);
        } catch (error) {
            alert(error.message || "Unable to fetch purchase items.");
        }
    });

    document.querySelectorAll("#purchase-return-items tbody tr").forEach(recalc);
})();
