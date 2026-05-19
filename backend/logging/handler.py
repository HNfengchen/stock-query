import os
import gzip
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime


class SizeAndTimeRotatingFileHandler(logging.Handler):
    def __init__(
        self,
        filename: str,
        max_bytes: int = 100 * 1024 * 1024,
        backup_count: int = 30,
        encoding: str = 'utf-8',
    ):
        super().__init__()
        self.base_filename = filename
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding

        log_dir = os.path.dirname(filename)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        self._current_date = datetime.now().strftime('%Y-%m-%d')
        self._current_handler = self._create_file_handler(filename)

    def _create_file_handler(self, filename: str) -> logging.FileHandler:
        handler = logging.FileHandler(filename, encoding=self.encoding)
        return handler

    def _get_dated_filename(self, date_str: str) -> str:
        base, ext = os.path.splitext(self.base_filename)
        return f'{base}.{date_str}{ext}'

    def _should_rotate_by_size(self) -> bool:
        try:
            if not os.path.exists(self.base_filename):
                return False
            return os.path.getsize(self.base_filename) >= self.max_bytes
        except OSError:
            return False

    def _should_rotate_by_date(self) -> bool:
        current_date = datetime.now().strftime('%Y-%m-%d')
        return current_date != self._current_date

    def _rotate(self) -> None:
        if not os.path.exists(self.base_filename):
            return

        self._current_handler.close()

        dated_filename = self._get_dated_filename(self._current_date)
        if os.path.exists(dated_filename):
            idx = 1
            while os.path.exists(f'{dated_filename}.{idx}'):
                idx += 1
            dated_filename = f'{dated_filename}.{idx}'

        os.rename(self.base_filename, dated_filename)
        self._compress_old_files()

        self._current_date = datetime.now().strftime('%Y-%m-%d')
        self._current_handler = self._create_file_handler(self.base_filename)

    def _compress_old_files(self) -> None:
        base_dir = os.path.dirname(self.base_filename)
        base_name = os.path.basename(self.base_filename)
        now = datetime.now()

        try:
            files = os.listdir(base_dir)
        except OSError:
            return

        dated_files = []
        for f in files:
            if f.startswith(base_name) and f != base_name:
                full_path = os.path.join(base_dir, f)
                if os.path.isfile(full_path) and not f.endswith('.gz'):
                    dated_files.append(full_path)

        dated_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        for i, filepath in enumerate(dated_files):
            if i >= self.backup_count:
                try:
                    os.remove(filepath)
                    gz_path = filepath + '.gz'
                    if os.path.exists(gz_path):
                        os.remove(gz_path)
                except OSError:
                    pass
            else:
                gz_path = filepath + '.gz'
                if not os.path.exists(gz_path):
                    try:
                        with open(filepath, 'rb') as f_in:
                            with gzip.open(gz_path, 'wb') as f_out:
                                f_out.writelines(f_in)
                        os.remove(filepath)
                    except OSError:
                        pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._should_rotate_by_date() or self._should_rotate_by_size():
                self._rotate()
            self._current_handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self._current_handler.close()
        except Exception:
            pass
        super().close()

    def setFormatter(self, fmt: logging.Formatter) -> None:
        super().setFormatter(fmt)
        self._current_handler.setFormatter(fmt)
