document.addEventListener("DOMContentLoaded", () => {
    const total = document.getElementById("total-amount");
    if (total) {
        let current = 0;
        const target = parseFloat(total.innerText);
        const step = target / 30;

        const anim = setInterval(() => {
            current += step;
            if (current >= target) {
                total.innerText = target.toFixed(2);
                clearInterval(anim);
            } else {
                total.innerText = current.toFixed(2);
            }
        }, 30);
    }
});
