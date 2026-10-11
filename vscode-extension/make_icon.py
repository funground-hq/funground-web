"""The funground extension's Marketplace icon (128 x 128 PNG): the first sketch's circle on the site's teal."""
import funground as f

f.size(128, 128)
f.background(0, 0, 0, 0)
f.no_stroke()
f.fill("#00897b")
f.rect(0, 0, 128, 128, 24)
f.fill("#ff6347")
f.circle(64, 64, 40)
f.save("icon.png")
