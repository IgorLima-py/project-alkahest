// vault/static/js/metacritic_widget.js
document.addEventListener('DOMContentLoaded', function() {
    const containers = document.querySelectorAll('.metacritic-widget-wrapper');

    containers.forEach(container => {
        const input = container.querySelector('input[type="hidden"]');
        const display = container.querySelector('.rating-display-circle span');
        const circle = container.querySelector('.rating-display-circle');
        const bars = container.querySelectorAll('.rating-bar');
        
        let currentRating = parseInt(input.value) || 0;
        updateVisuals(currentRating);

        bars.forEach(bar => {
            // Hover: mostra a nota temporária
            bar.addEventListener('mouseenter', () => {
                const val = parseInt(bar.getAttribute('data-value'));
                updateVisuals(val, true); // true = preview mode
            });

            // Click: fixa a nota
            bar.addEventListener('click', () => {
                currentRating = parseInt(bar.getAttribute('data-value'));
                input.value = currentRating;
                updateVisuals(currentRating);
            });
        });

        // Mouse leave: volta para a nota selecionada
        container.querySelector('.bars-container').addEventListener('mouseleave', () => {
            updateVisuals(currentRating);
        });

        function updateVisuals(val, preview = false) {
            // Atualiza Texto (0-10)
            display.textContent = val > 0 ? (val / 10) : '-';
            
            // Atualiza Cor do Círculo
            circle.className = 'rating-display-circle'; // Reset
            if (val === 0) circle.classList.add('bg-secondary');
            else if (val < 40) circle.classList.add('bg-danger-custom');
            else if (val < 70) circle.classList.add('bg-warning-custom');
            else if (val < 90) circle.classList.add('bg-success-custom');
            else circle.classList.add('bg-purple-custom');

            // Atualiza Barras
            bars.forEach(bar => {
                const barVal = parseInt(bar.getAttribute('data-value'));
                bar.classList.remove('active', 'selected');
                
                // Se a barra for menor ou igual ao valor atual, ela acende
                if (barVal <= val) {
                     if (!preview) bar.classList.add('selected');
                     else bar.classList.add('active');
                }
            });
        }
    });
});
