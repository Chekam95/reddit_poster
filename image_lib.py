import io
import math
import os
import random
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import piexif
import hashlib
import copy
from dateutil.relativedelta import relativedelta
from pillow_heif import register_heif_opener

from cv2 import imread, imwrite


# Function to generate a random name in the range [1000, 1500]
def generate_random_name():
    return f"IMG_{random.randint(1000, 9000)}"


def rotate_image(image, angle):
    """
    Rotates an OpenCV 2 / NumPy image about it's centre by the given angle
    (in degrees). The returned image will be large enough to hold the entire
    new image, with a black background
    """

    # Get the image size
    # No that's not an error - NumPy stores image matricies backwards
    image_size = (image.shape[1], image.shape[0])
    image_center = tuple(np.array(image_size) / 2)

    # Convert the OpenCV 3x2 rotation matrix to 3x3
    rot_mat = np.vstack(
        [cv2.getRotationMatrix2D(image_center, angle, 1.0), [0, 0, 1]]
    )

    rot_mat_notranslate = np.matrix(rot_mat[0:2, 0:2])

    # Shorthand for below calcs
    image_w2 = image_size[0] * 0.5
    image_h2 = image_size[1] * 0.5

    # Obtain the rotated coordinates of the image corners
    rotated_coords = [
        (np.array([-image_w2, image_h2]) * rot_mat_notranslate).A[0],
        (np.array([image_w2, image_h2]) * rot_mat_notranslate).A[0],
        (np.array([-image_w2, -image_h2]) * rot_mat_notranslate).A[0],
        (np.array([image_w2, -image_h2]) * rot_mat_notranslate).A[0]
    ]

    # Find the size of the new image
    x_coords = [pt[0] for pt in rotated_coords]
    x_pos = [x for x in x_coords if x > 0]
    x_neg = [x for x in x_coords if x < 0]

    y_coords = [pt[1] for pt in rotated_coords]
    y_pos = [y for y in y_coords if y > 0]
    y_neg = [y for y in y_coords if y < 0]

    right_bound = max(x_pos)
    left_bound = min(x_neg)
    top_bound = max(y_pos)
    bot_bound = min(y_neg)

    new_w = int(abs(right_bound - left_bound))
    new_h = int(abs(top_bound - bot_bound))

    # We require a translation matrix to keep the image centred
    trans_mat = np.matrix([
        [1, 0, int(new_w * 0.5 - image_w2)],
        [0, 1, int(new_h * 0.5 - image_h2)],
        [0, 0, 1]
    ])

    # Compute the tranform for the combined rotation and translation
    affine_mat = (np.matrix(trans_mat) * np.matrix(rot_mat))[0:2, :]

    # Apply the transform
    result = cv2.warpAffine(
        image,
        affine_mat,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR
    )

    return result


def largest_rotated_rect(w, h, angle):
    """
    Given a rectangle of size wxh that has been rotated by 'angle' (in
    radians), computes the width and height of the largest possible
    axis-aligned rectangle within the rotated rectangle.

    Original JS code by 'Andri' and Magnus Hoff from Stack Overflow

    Converted to Python by Aaron Snoswell
    """

    quadrant = int(math.floor(angle / (math.pi / 2))) & 3
    sign_alpha = angle if ((quadrant & 1) == 0) else math.pi - angle
    alpha = (sign_alpha % math.pi + math.pi) % math.pi

    bb_w = w * math.cos(alpha) + h * math.sin(alpha)
    bb_h = w * math.sin(alpha) + h * math.cos(alpha)

    gamma = math.atan2(bb_w, bb_w) if (w < h) else math.atan2(bb_w, bb_w)

    delta = math.pi - alpha - gamma

    length = h if (w < h) else w

    d = length * math.cos(alpha)
    a = d * math.sin(alpha) / math.sin(delta)

    y = a * math.cos(gamma)
    x = y * math.tan(gamma)

    return (
        bb_w - 2 * x,
        bb_h - 2 * y
    )


def crop_around_center(image, width, height):
    """
    Given a NumPy / OpenCV 2 image, crops it to the given width and height,
    around it's centre point
    """

    image_size = (image.shape[1], image.shape[0])
    image_center = (int(image_size[0] * 0.5), int(image_size[1] * 0.5))

    if (width > image_size[0]):
        width = image_size[0]

    if (height > image_size[1]):
        height = image_size[1]

    x1 = int(image_center[0] - width * 0.5)
    x2 = int(image_center[0] + width * 0.5)
    y1 = int(image_center[1] - height * 0.5)
    y2 = int(image_center[1] + height * 0.5)

    return image[y1:y2, x1:x2]


def get_new_exif(width, height, pil_image=None):
    # lat = round(lat, 2)
    # lng = round(lng, 2)
    time_now = datetime.now() - relativedelta(months=random.randint(0, 1),
                                              days=random.randint(1, 15),
                                              hours=random.randint(4, 9),
                                              minutes=random.randint(5, 15),
                                              seconds=random.randint(0, 30))
    formatted_time = time_now.strftime('%Y:%m:%d %H:%M:%S')
    gps_time = time_now.strftime('%Y:%m:%d')
    hour = int(time_now.strftime('%H'))
    min = int(time_now.strftime('%m'))
    random_utc = bytes(f"-0{random.randint(2, 9)}:00", 'utf-8')
    th_info = {
        271: b'Apple',
        272: b'iPhone 15 Pro Max',
        274: 1,
        282: (72, 1),
        283: (72, 1),
        296: 2,
        305: b'17.2.1',
        306: bytes(formatted_time, 'utf-8'),
        316: b'iPhone 15 Pro Max',
        34665: 232,
        34853: 2390
    }
    exif_info = {
        33434: (1, random.randint(30, 80)),
        33437: (random.randint(4, 8), random.randint(5, 10)),
        34850: 2,
        34855: random.choice([100, 125, 400, 800]),
        36864: b'0232',
        36867: bytes(formatted_time, 'utf-8'),
        36868: bytes(formatted_time, 'utf-8'),
        36880: random_utc,
        36881: random_utc,
        36882: random_utc,
        37377: (random.randint(50000, 57000), random.randint(8900, 8999)),
        37378: (random.randint(14000, 14699), random.randint(10000, 10999)),
        37379: (random.randint(15000, 15999), random.randint(7000, 7500)),
        37380: (0, 1),
        37383: random.choice([2, 3, 4, 5]),
        37385: 16,
        37386: (random.randint(43, 59), random.randint(6, 14)),
        37396: (
            random.randint(1950, 2100), random.randint(1400, 1600), random.randint(2200, 2399),
            random.randint(1700, 2300)),
        37500: b'Apple iOS\x00\x00\x01MM\x00/\x00\x01\x00\t\x00\x00\x00\x01\x00\x00\x00\x0e\x00\x02\x00\x07\x00\x00\x02\x00\x00\x00\x02H\x00\x03\x00\x07\x00\x00\x00h\x00\x00\x04H\x00\x04\x00\t\x00\x00\x00\x01\x00\x00\x00\x01\x00\x05\x00\t\x00\x00\x00\x01\x00\x00\x00\xa7\x00\x06\x00\t\x00\x00\x00\x01\x00\x00\x00\xae\x00\x07\x00\t\x00\x00\x00\x01\x00\x00\x00\x01\x00\x08\x00\n\x00\x00\x00\x03\x00\x00\x04\xb0\x00\x0c\x00\n\x00\x00\x00\x02\x00\x00\x04\xc8\x00\r\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00\x0e\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00\x10\x00\t\x00\x00\x00\x01\x00\x00\x00\x01\x00\x14\x00\t\x00\x00\x00\x01\x00\x00\x00\x0c\x00\x17\x00\x10\x00\x00\x00\x01\x00\x00\x04\xd8\x00\x19\x00\t\x00\x00\x00\x01\x00\x00 \x02\x00\x1a\x00\x02\x00\x00\x00\x06\x00\x00\x04\xe0\x00\x1f\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00 \x00\x02\x00\x00\x00%\x00\x00\x04\xe6\x00!\x00\n\x00\x00\x00\x01\x00\x00\x05\x0b\x00#\x00\t\x00\x00\x00\x02\x00\x00\x05\x13\x00%\x00\x10\x00\x00\x00\x01\x00\x00\x05\x1b\x00&\x00\t\x00\x00\x00\x01\x00\x00\x00\x03\x00\'\x00\n\x00\x00\x00\x01\x00\x00\x05#\x00+\x00\x02\x00\x00\x00%\x00\x00\x05+\x00-\x00\t\x00\x00\x00\x01\x00\x00\x0e\xa4\x00.\x00\t\x00\x00\x00\x01\x00\x00\x00\x01\x00/\x00\t\x00\x00\x00\x01\x00\x00\x00L\x000\x00\n\x00\x00\x00\x01\x00\x00\x05P\x003\x00\t\x00\x00\x00\x01\x00\x000\x00\x004\x00\t\x00\x00\x00\x01\x00\x00\x00\x05\x005\x00\t\x00\x00\x00\x01\x00\x00\x00\x04\x006\x00\t\x00\x00\x00\x01\x00\x00\x01P\x007\x00\t\x00\x00\x00\x01\x00\x00\x00\x04\x008\x00\t\x00\x00\x00\x01\x00\x00\x00\xd0\x009\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00:\x00\t\x00\x00\x00\x01\x00\x00\x00\x04\x00;\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00<\x00\t\x00\x00\x00\x01\x00\x00\x00\x04\x00=\x00\t\x00\x00\x00\x01\x00\x00\x00%\x00A\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00B\x00\t\x00\x00\x00\x01\x00\x00\x00\x00\x00J\x00\t\x00\x00\x00\x01\x00\x00\x00\x02\x00M\x00\n\x00\x00\x00\x01\x00\x00\x05X\x00N\x00\x07\x00\x00\x00y\x00\x00\x05`\x00O\x00\x07\x00\x00\x00+\x00\x00\x05\xd9\x00R\x00\t\x00\x00\x00\x01\x00\x00\x00\x06\x00S\x00\t\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00i\x00\x82\x00\x80\x00g\x00E\x00,\x00\x1d\x000\x004\x00/\x00*\x00&\x00!\x00\x1c\x00\x17\x00\x13\x00x\x00\xa0\x00\xa4\x00\x84\x00U\x003\x00!\x00*\x00,\x00.\x00+\x00%\x00 \x00\x1a\x00\x17\x00\x14\x00\x87\x00\xc3\x00\xd9\x00\xb2\x00n\x00<\x00 \x00/\x004\x001\x00,\x00&\x00 \x00\x19\x00\x16\x00\x14\x00\x97\x00\xf1\x00.\x01\xfb\x00\x95\x00H\x00#\x00.\x000\x00/\x00+\x00%\x00\x1e\x00\x18\x00\x15\x00\x13\x00\xbc\x00E\x01\xd6\x01\x94\x01\xd3\x00Y\x00&\x00.\x003\x00-\x00,\x00\'\x00\x1f\x00\x18\x00\x15\x00\x12\x00\xfd\x00\x9e\x01\xb4\x02f\x02%\x01h\x00(\x00,\x002\x000\x00.\x00*\x00#\x00\x1b\x00\x18\x00\x14\x00X\x01\xfc\x01k\x03J\x03\xa6\x01\x84\x00-\x00+\x002\x00/\x00.\x00+\x00 \x00\x1c\x00\x17\x00\x15\x00\xc1\x01\xb1\x02\xd6\x03\xd3\x03k\x02\xf4\x01<\x00/\x002\x001\x000\x00*\x00%\x00 \x00\x1a\x00\x16\x00\x1a\x02p\x03\xed\x03\xff\x03\xa2\x02P\x01?\x001\x003\x00/\x00,\x00(\x00$\x00 \x00\x17\x00\x12\x00_\x02\xa8\x03\x82\x03\xa4\x03\x84\x032\x01q\x00-\x001\x00,\x00 \x00\x1b\x00\x18\x00\x16\x00\x12\x00\x0e\x00v\x02\xaa\x03\x92\x03\xd5\x03P\x03\x99\x01\x86\x00*\x006\x00/\x00\'\x00!\x00\x1b\x00\x14\x00\x0f\x00\x0c\x00b\x02~\x03\xef\x03\xe1\x03a\x02t\x02Z\x01*\x002\x00.\x00%\x00"\x00\x1e\x00\x19\x00\x13\x00\x0e\x00\x10\x02Q\x03\xef\x03\xed\x03\x94\x02\x1b\x01e\x00$\x00.\x00\'\x00 \x00\x1d\x00\x1a\x00\x17\x00\x13\x00\x0f\x00\xca\x01\x10\x03\xa2\x03\xa2\x03\x1f\x02\xa3\x00;\x00"\x00)\x00#\x00$\x00\x1e\x00\x1a\x00\x15\x00\x15\x00\x14\x00\x97\x01\x8c\x02!\x03\x0e\x03\x90\x01|\x001\x00%\x00\x1d\x00\x13\x00\x15\x00\x13\x00\t\x00\n\x00\n\x00\t\x00a\x01\x03\x02I\x028\x02\x17\x01c\x00+\x00#\x00\x1c\x00\x0e\x00\x0c\x00\n\x00\t\x00\x1f\x00\x15\x00\t\x00bplist00\xd4\x01\x02\x03\x04\x05\x06\x07\x08UflagsUvalueYtimescaleUepoch\x10\x01\x13\x00\x00\x1a\xd5\x8c]Fe\x12;\x9a\xca\x00\x10\x00\x08\x11\x17\x1d\'-/8=\x00\x00\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\t\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00?\x00\x00\x06\x11\x00\x00\xe4\xd5\xff\xffs\xe9\x00\x00\x90!\x00\x00 \xff\x00\x00\xe7\xee\x00\x00\x00\x85\x00\x00\x00\x80\x00\x00\x00\xc1\x00\x00\x00\x80\x00\x00\x00\x00BP \x00q825s\x000932352C-38C2-4F49-BDF0-0549C4FE4E0A\x00\x00\x00\xf9A\x00\x01\'\x9a\x00\x00\x00\xbc\x10\x00\x00#\x00\x00\x00\x00\x00\x00\x10\x8e\x00\x06^\xab\x00\x00*\x9e340FBF5E-AF4A-430D-AA3E-3FC9E35B8317\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x88\x0b\x00\x00\x04\x00bplist00\xd2\x01\x02\x03\x04Q1Q2\x10\x01\xa2\x05\n\xd2\x06\x07\x08\tS2.1S2.2#@I\x06p\x00\x00\x00\x00#@\xdc=@\x00\x00\x00\x00\xd2\x06\x07\x0b\x0c#\x00\x00\x00\x00\x00\x00\x00\x00#@E\x00\x00\x00\x00\x00\x00\x08\r\x0f\x11\x13\x16\x1b\x1f#,5:C\x00\x00\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00Lbplist00\x10\x00\x08\x00\x00\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\n',
        37521: b'994',
        37522: b'994',
        40961: 65535,
        40962: width,
        40963: height,
        41495: 2,
        41729: b'\x01',
        41986: random.choice([0, 1, 2]),
        41987: 0,
        41989: random.randint(20, 30),
        42034: ((807365, 524263), (15, 2), (8, 5), (12, 5)),
        42035: b'Apple',
        42036: b'iPhone 15 Pro Max back triple camera 5.1mm f/1.6'
    }
    # first_value = b'N'
    # if lat < 0:
    #     first_value = b'S'
    #     lat = lat * -1
    # second_value = b'E'
    # if lng < 0:
    #     second_value = b'W'
    #     lng = lng * -1
    # gps_info = {
    #     1: first_value,
    #     2: ((int(lat), 1), (random.randint(0, 99), 1), (2666, 100)),
    #     3: second_value,
    #     4: ((int(lng), 1), (random.randint(0, 99), 1), (410, 100)),
    #     5: 0,
    #     6: (random.randint(240000, 260000), random.randint(1900, 2200)),
    #     7: ((hour, 1), (min, 1), (3314, 100)),
    #     12: b'K',
    #     13: (0, 1),
    #     16: b'T',
    #     17: (random.randint(652483, 682483), random.randint(2000, 2100)),
    #     23: b'T',
    #     24: (random.randint(650000, 653000), random.randint(2000, 2100)),
    #     29: bytes(gps_time, 'utf-8'),
    #     31: (random.randint(117000, 118999), random.randint(4300, 4400))
    # }
    copy_photo = copy.deepcopy(pil_image)
    copy_photo.thumbnail((160, 120), Image.Resampling.LANCZOS)
    imgByteArr = io.BytesIO()
    copy_photo.save(imgByteArr, format=copy_photo.format)
    imgByteArr = imgByteArr.getvalue()
    ready_exif = {
        "0th": th_info,
        "Exif": exif_info,
        "GPS": {},
        "Interop": {},
        "1st": {
            259: 6,
            282: (72, 1),
            283: (72, 1),
            296: 2,
            513: 1814,
            514: random.randint(10744, 15000)
        },
        "thumbnail": imgByteArr
    }
    return ready_exif


def modify_exif_shooted_older(file_path, points):
    try:
        img = Image.open(file_path)
        img.save(file_path,
                 exif=piexif.dump(
                     get_new_exif(width=img.width, height=img.height, pil_image=img)))
    except Exception as e:
        print("modify_exif_shooted_older error ", e)


def making_decision(percent):
    return random.randrange(100) < int(percent)


def noise(in_path):
    # Random noise
    try:
        img = imread(in_path)
        noise = np.random.normal(0, random.uniform(1, 3), img.shape)
        img_noised = img + noise
        img_noised = np.clip(img_noised, 0, 255).astype(np.uint8)
        imwrite(in_path, img_noised)
    except Exception:
        print("ERROR noise")



# Function to apply various random image transformations
def apply_random_transformations(image):
    try:
        # Random resolution change (increase or decrease)
        resolution_factor = random.randint(90, 120) / 100  # Random integer between 80 and 120
        new_width = int(image.width * resolution_factor)
        new_height = int(image.height * resolution_factor)
        image = image.resize((new_width, new_height))

        # Random crop
        box = (random.randint(0, 220),
               random.randint(0, 220),
               image.width - random.randint(0, 220),
               image.height - random.randint(0, 220))
        image.crop(box)

        # Random brightness change
        brightness_factor = random.randint(70, 120) / 100  # Random integer between 80 and 120
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(brightness_factor)

        # Random contrast 130
        contrast_factor = random.randint(70, 130) / 100  # Random integer between 80 and 120
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(contrast_factor)

        # Random color (saturation) change
        saturation_factor = random.randint(80, 120) / 100  # Random integer between 80 and 120
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance(saturation_factor)

        # Random sharpness change
        sharpness_factor = random.randint(70, 120) / 100  # Random integer between 80 and 120
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(sharpness_factor)

        # Random blur change
        image = image.filter(ImageFilter.GaussianBlur(random.uniform(0.02, 0.25)))

        # Random DPI change (if it exists)
        if "dpi" in image.info:
            dpi_factor = random.randint(85, 110) / 100  # Random integer between 80 and 120
            dpi_x, dpi_y = image.info["dpi"]
            image.info["dpi"] = (
                int(dpi_x * dpi_factor),
                int(dpi_y * dpi_factor),
            )
        return image
    except Exception as e:
        print(f"Error applying random transformations: {e}")
        return None


def resize_image(input_image):
    new_width, new_height = 3024, 4032
    image = Image.open(input_image)
    width, height = image.size
    aspect_ratio = width / height
    target_aspect_ratio = new_width / new_height
    if aspect_ratio > target_aspect_ratio:
        crop_width = height * target_aspect_ratio
        left = (width - crop_width) / 2
        top = 0
        right = (width + crop_width) / 2
        bottom = height
    else:
        crop_height = width / target_aspect_ratio
        left = 0
        top = (height - crop_height) / 2
        right = width
        bottom = (height + crop_height) / 2
    image = image.crop((left, top, right, bottom))
    image = image.resize((new_width, new_height))
    image.save(input_image)


def process_image(input_image_path, make_photo_now=False, points=None):
    print("Processing image!")
    if points is None:
        points = {}
    try:
        old_name = os.path.basename(input_image_path)
        noise(input_image_path)
        img = Image.open(input_image_path).convert("RGB")
        img = apply_random_transformations(img)
        new_name = generate_random_name()
        new_file_path = f"temp/{new_name}.jpeg"
        img.save(new_file_path)
        input_image_path = os.path.abspath(new_file_path)
        image = cv2.imread(input_image_path)
        angle = random.uniform(-6., 6.)
        image_height, image_width = image.shape[0:2]
        image = rotate_image(image, angle)
        image_rotated_cropped = crop_around_center(
            image,
            *largest_rotated_rect(
                image_width,
                image_height,
                math.radians(angle)
            )
        )
        noise(input_image_path)
        cv2.imwrite(input_image_path, image_rotated_cropped)
        # if making_decision(50):
        #     if make_photo_now:
        #         modify_exif_shooted(f"{new_path}/{new_name}.jpg")
        #     else:
        resize_image(input_image_path)
        noise(input_image_path)
        change_metadata(input_image_path, new_name)
        modify_exif_shooted_older(input_image_path, points)
        change_md5(input_image_path)
        return input_image_path
    except Exception as e:
        print(f"Error processing {input_image_path}: {e}")
        return None


def change_metadata(image_path, new_name):
    try:
        exif_dict = piexif.load(image_path)
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = new_name.encode("utf-8")
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path)
    except Exception as e:
        print(f"Error changing metadata for {image_path}: {e}")


# Function to change MD5 hash of an image
def change_md5(image_path):
    try:
        with open(image_path, 'rb') as f:
            data = f.read()
        new_md5 = hashlib.md5(data).hexdigest()
        new_data = data.replace(b'MD5=', f'MD5={new_md5}'.encode())
        with open(image_path, 'wb') as f:
            f.write(new_data)
    except Exception as e:
        print(f"Error changing MD5 for {image_path}: {e}")


def input_image_path(image_path):
    result = process_image(image_path)
    return result

# if __name__ == "__main__":
#     # Змініть шлях до зображення на звичайний шлях
#     input_image_path = "/Users/oksana/Downloads/IMG_1035.jpg"
#
#     # Перевіряємо, чи існує файл за цим шляхом
#     if not os.path.isfile(input_image_path):
#         print(f"Файл не знайдено: {input_image_path}")
#     else:
#         processed_image_path = process_image(input_image_path)
#
#         if processed_image_path:
#             print(f"Зображення успішно оброблено: {processed_image_path}")
#         else:
#             print("Помилка при обробці зображення.")
