(function () {
  const invoiceSelect = document.getElementById("receipt-invoice");
  const amountInput = document.getElementById("receipt-amount");
  if (!invoiceSelect || !amountInput || amountInput.readOnly) return;
  invoiceSelect.addEventListener("change", function () {
    const option = invoiceSelect.selectedOptions[0];
    const balance = option ? option.getAttribute("data-balance") : "";
    if (balance) amountInput.value = Number(balance).toFixed(2);
  });
})();
