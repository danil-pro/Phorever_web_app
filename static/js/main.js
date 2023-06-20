$(document).ready(function() {
    $('.photo-checkbox').change(function() {
        var anyChecked = false;
        $('.photo-checkbox').each(function() {
            if ($(this).is(':checked')) {
                anyChecked = true;
                return false;
            }
        });

        if (anyChecked) {
            $('.fixed-menu').show();
        } else {
            $('.fixed-menu').hide();
        }
    });
});

$(document).ready(function() {
    $('input[type="checkbox"]').change(function() {
      var selectedValues = [];
      $('input[type="checkbox"]:checked').each(function() {
        selectedValues.push($(this).val());
      });
      $('.hidden_selected_photos').val(selectedValues.join(','));
    });
});


