# noinspection PyPackageRequirements
from PIL import Image, ImageFont, ImageDraw


class RangeMap(object):

    def __init__(self, default_value):
        self._default = default_value
        self._rules = []

    def add_rule(self, start, end, value):
        self._rules.insert(0, (start, end, value))

    def get(self, key):
        for r in self._rules:
            start, end, value = r
            if start <= key <= end:
                return value
        return self._default


class Pen(object):

    def __init__(self, max_size, min_size, default_font):
        """
        Create a new one.
        """
        self._image = None
        """:type : Optional[Image.Image]"""
        self._ctx = None
        """:type : Optional[ImageDraw.ImageDraw]"""
        self._fg_color = "black"
        self._bg_color = "white"
        self._pos_x = 0
        self._pos_y = 0
        self._right_bound = 0
        self._left_bound = 0
        self._top_bound = 0
        self._bottom_bound = 0
        self._default_font = default_font
        self._fonts = RangeMap(default_font)
        self.max_font_size = max_size
        self.min_font_size = min_size
        self.line_spacing = 2
        self.border_width = 1
        self.kerning = 2
        self.word_spacing_factor = 1.5

    # noinspection PyMethodMayBeStatic
    def draw_meme_text(self, im, upper, lower):
        self.set_image(im)
        self.draw_top_aligned_text(upper)
        if lower is not None and lower != '':
            self.draw_bottom_aligned_text(lower)

    def set_image(self, im):
        self._image = im
        self._ctx = ImageDraw.Draw(im, mode="RGBA")
        self._right_bound = im.width - 1
        self._bottom_bound = im.height - 1

    def set_color(self, fg=None, bg=None):
        if fg is not None:
            self._fg_color = fg
        if bg is not None:
            self._bg_color = bg

    def get_color(self):
        """
        Return a tuple containing foreground and background colors.
        :rtype: (Any, Any)
        :return: The tuple
        """
        return self._fg_color, self._bg_color

    def set_font_mapping(self, path, codepoint_start, codepoint_end):
        self._fonts.add_rule(codepoint_start, codepoint_end, path)

    def set_right_bound(self, bound):
        self._right_bound = bound

    def set_bottom_bound(self, bound):
        self._bottom_bound = bound

    def set_position(self, x=None, y=None):
        if x is not None:
            self._pos_x = x
        if y is not None:
            self._pos_y = y

    def draw_top_aligned_text(self, text):
        max_width = (self._right_bound - self._left_bound + 1) - (4 * self.border_width)
        lines, f_size = self._wrap_text(text, max_width)

        true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
        line_height = true_line_height + self.line_spacing
        line_num = 0
        for line in lines:
            line_width = self._get_render_width(line, f_size)
            offset_x = round((max_width - line_width) / 2)
            offset_y = round(self.line_spacing / 2)
            y = self._top_bound + (line_num * line_height) + offset_y
            x = offset_x
            self._draw_text(x, y, line, f_size)
            line_num += 1

    def draw_bottom_aligned_text(self, text):
        max_width = (self._right_bound - self._left_bound + 1) - (4 * self.border_width)
        lines, f_size = self._wrap_text(text, max_width)

        true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
        line_height = true_line_height + self.line_spacing
        line_num = 0
        for line in lines:
            line_width = self._get_render_width(line, f_size)
            offset_x = round((max_width - line_width) / 2)
            offset_y = round(self.line_spacing / 2)
            y = self._bottom_bound - (line_height * (len(lines) - line_num)) + offset_y
            x = offset_x
            self._draw_text(x, y, line, f_size)
            line_num += 1

    def draw_solid_rect(self, dx, dy):
        if self._image is None:
            raise ValueError("no image set")
        self._ctx.rectangle(xy=[self._pos_x, self._pos_y, self._pos_x+dx, self._pos_y+dy], fill=self._fg_color)
        self._pos_x += dx
        self._pos_y += dy

    def draw_image_rect(self, dx, dy, im: Image.Image):
        """Draw an image on the current image."""

        if self._image is None:
            raise ValueError("no image set")

        new_width = abs(dx - self._pos_x)
        ratio = new_width / float(im.width)
        new_height = round(im.height * ratio)
        if ratio > 1:
            resample_algo = Image.HAMMING
        else:
            resample_algo = Image.LANCZOS
        im = im.resize((new_width, new_height), resample_algo)
        self._image.paste(im=im, box=(self._pos_x, self._pos_x + dx, self._pos_y, self._pos_y + dy))

    def _draw_text(self, x, y, text, size):
        cur_x = x
        cur_y = y
        first_char = False
        for ch in text:
            if first_char:
                first_char = False
            else:
                cur_x += self.kerning * self.font_size_ratio(size)

            f = ImageFont.truetype(self._fonts.get(ord(ch)), size=size)
            b = self.border_width * self.font_size_ratio(size)
            if 0 < b < 1:
                b = 1

            ch_width = f.getsize(ch)[0]

            if ch != ' ':
                self._ctx.text((cur_x - b, cur_y - b), ch, font=f, fill=self._bg_color)
                self._ctx.text((cur_x + b, cur_y - b), ch, font=f, fill=self._bg_color)
                self._ctx.text((cur_x - b, cur_y + b), ch, font=f, fill=self._bg_color)
                self._ctx.text((cur_x + b, cur_y + b), ch, font=f, fill=self._bg_color)

                self._ctx.text((cur_x, cur_y), ch, font=f, fill=self._fg_color)
            else:
                ch_width *= self.word_spacing_factor

            cur_x += ch_width

    def _wrap_text(self, text, width):
        if len(text) == 0:
            return [""]

        # first try to fit the whole thing on one line:
        fit_text, more_text_remains, remaining, f_size = self._fit_to_line(
            text, width, self.max_font_size, self.min_font_size
        )

        while len(fit_text) == 0 and len(text) != 0:
            # uh-oh, looks like the line is too big to fit on the line! so modify the text and start subdividing the
            # first word until it works
            first_word_end = text.find(' ')
            if first_word_end == -1:
                first_word_end = len(text)
            split_idx = first_word_end // 2
            text = text[:split_idx] + '- -' + text[split_idx:]

            fit_text, more_text_remains, remaining, f_size = self._fit_to_line(
                text, width, self.max_font_size, self.min_font_size
            )

        lines = [fit_text]
        # then it didn't fit, so repeat for all remaining lines
        while more_text_remains:
            size = self.min_font_size
            fit_text, more_text_remains, remaining, f_size = self._fit_to_line(remaining, width, size, size)

            while len(fit_text) == 0 and more_text_remains:
                # uh-oh, looks like the line is too big to fit on the line! so modify the text and start subdividing the
                # first word until it works
                first_word_end = remaining.find(' ')
                if first_word_end == -1:
                    first_word_end = len(remaining)
                split_idx = first_word_end // 2
                remaining = remaining[:split_idx] + '- -' + remaining[split_idx:]

                fit_text, more_text_remains, remaining, f_size = self._fit_to_line(remaining, width, size, size)

            lines.append(fit_text)

        return lines, f_size

    def _fit_to_line(self, text, max_width, max_font_size, min_font_size):
        """
        Fits the given text to a line. Breaks words too large to fit on to the next line.
        :param text: The text to fit.
        :param max_width: The maximum width of a line.
        :param max_font_size: The maximum size the font can be.
        :param min_font_size: The minimum size the font can be.

        :return: A tuple.
        The line, whether there is more text, the rest of the text, the font size of the final version.
        """
        line_so_far = ''
        more_lines = False
        font_size = 0
        working_text = text
        for font_size in range(max_font_size, min_font_size - 1, -1):
            line_so_far = ""
            working_text = text
            length_so_far = 0
            space_chars = 0
            more_lines = False
            first_word = True
            while True:
                word_end = self._find_next_break(working_text)
                next_word = working_text[:word_end]
                next_word_len = self._get_render_width((' ' * space_chars) + next_word, font_size)
                if first_word:
                    first_word = False
                else:
                    next_word_len += self.kerning * self.font_size_ratio(font_size)
                if length_so_far + next_word_len <= max_width:
                    line_so_far += (' ' * space_chars) + next_word
                    length_so_far += next_word_len
                else:
                    more_lines = True
                    break

                # find next space for adding to next word
                space_chars = 0
                while word_end < len(working_text) and self._is_space(working_text[word_end]):
                    space_chars += 1
                    word_end += 1

                if word_end != len(working_text):
                    working_text = working_text[word_end:]
                else:
                    break
            if not more_lines:
                break
        return line_so_far, more_lines, working_text if more_lines else '', font_size

    def _find_next_break(self, text):
        import unicodedata
        idx = -1
        for ch in text:
            idx += 1
            cat = unicodedata.category(ch)
            if cat == 'Lo':
                return idx + 1
            elif self._is_space(ch):
                return idx
        return len(text)

    # noinspection PyMethodMayBeStatic
    def _is_space(self, ch):
        import unicodedata
        cat = unicodedata.category(ch)
        return cat.startswith('Z') or ch == '\n' or ch == '\t' or ch == '\r'

    def _get_render_width(self, word, font_size):
        total_size = 0
        first_char = True
        for ch in word:
            if first_char:
                first_char = False
            else:
                total_size += self.kerning * self.font_size_ratio(font_size)
            font_name = self._fonts.get(ord(ch))
            f = ImageFont.truetype(font_name, font_size)
            ch_width = f.getsize(ch)[0]

            if ch == ' ':
                ch_width *= self.word_spacing_factor

            total_size += ch_width
        return total_size

    def font_size_ratio(self, cur):
        return cur / float(self.max_font_size)
