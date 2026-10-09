import funground as f

mic = f.microphone()


def setup():
    f.size(320, 200)
    mic.start()


def draw():
    f.background("black")
    f.fill("lime")
    f.rect(20, 80, 280 * mic.level(), 40)


f.run()
