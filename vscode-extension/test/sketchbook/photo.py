import funground as f

photo = f.load_image("data/photo.png")       # from the data folder beside this file


def setup():
    f.size(640, 400)


def draw():
    f.background("ivory")
    f.image(photo, 20, 20)                    # full size, so its pixels can be checked one by one


f.run()
