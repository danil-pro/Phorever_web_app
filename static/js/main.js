document.addEventListener("DOMContentLoaded", function() {
  const modals = document.querySelectorAll(".modal");
  const closeButtons = document.querySelectorAll(".close-button");
  const UpdateCloseButtons = document.querySelectorAll(".update-close-button");
  const updateButtons = document.querySelectorAll(".update-button");
  let openedModal = null;

  modals.forEach(function(modal) {
    const target = document.getElementById(modal.dataset.target);

    modal.addEventListener("click", function() {
      if (openedModal) {
        return; // Если есть открытое окно, выходим из функции
      }

      target.style.display = "block";
      openedModal = target;
    });
  });

  closeButtons.forEach(function(closeButton) {
    closeButton.addEventListener("click", function() {
      const modalContent = closeButton.closest(".modal-content");
      modalContent.style.display = "none";
      openedModal = null; // Сбрасываем открытое окно
    });
  });

  UpdateCloseButtons.forEach(function(UpdateCloseButtons) {
    UpdateCloseButtons.addEventListener("click", function() {
      const UpdateFormContent = UpdateCloseButtons.closest(".update-form");
      UpdateFormContent.style.display = "none";
      openedModal = null; // Сбрасываем открытое окно
    });
  });

  updateButtons.forEach(function(updateButton) {
    updateButton.addEventListener("click", function() {
      const modalContent = updateButton.closest(".modal-content");
      const photoId = modalContent.id.split("-")[1]; // Получаем ID фотографии из ID модального окна
      const updateForm = document.getElementById("update-form-" + photoId);

      modalContent.style.display = "none";
      updateForm.style.display = "block";
    });
  });
});




