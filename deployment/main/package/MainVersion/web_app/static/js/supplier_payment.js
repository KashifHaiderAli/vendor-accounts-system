(function () {
  const purchaseSelect = document.getElementById("supplier-payment-purchase");
  const amountInput = document.getElementById("supplier-payment-amount");
  if (!purchaseSelect || !amountInput || amountInput.readOnly) return;
  purchaseSelect.addEventListener("change", function () {
    const option = purchaseSelect.selectedOptions[0];
    const balance = option ? option.getAttribute("data-balance") : "";
    if (balance) amountInput.value = Number(balance).toFixed(2);
  });
})();
