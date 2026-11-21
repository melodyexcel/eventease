console.log("EventEase is running!"); 

function startCountdowns() {
    document.querySelectorAll('.countdown').forEach(function (el) {
        var target = new Date(el.dataset.date).getTime();
        var timer;
        function tick() {
            var diff = target - Date.now();
            if (diff <= 0) {
                el.textContent = 'Event started';
                clearInterval(timer);
                return;
            }
            var d = Math.floor(diff / 86400000);
            var h = Math.floor((diff % 86400000) / 3600000);
            var m = Math.floor((diff % 3600000) / 60000);
            var s = Math.floor((diff % 60000) / 1000);
            el.textContent = d + 'd ' + h + 'h ' + m + 'm ' + s + 's';
        }
        tick();
        timer = setInterval(tick, 1000);
    });
}
document.addEventListener('DOMContentLoaded', startCountdowns);
