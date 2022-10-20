import socket
import threading
from models.config import Config
from models.target import Target


class RequestHandlder:

    def __init__(self, connection: socket.socket, config: Config) -> None:
        self.target: Target = config.load_balancer.next()
        self.connection: socket.socket = connection
        self.request_data_pool: bytes = bytes()
        self.response_data_pool: bytes = bytes()
        self.config: Config = config
        self.SEPARATOR = b'\r\n\r\n'

    def run(self) -> None:
        threading.Thread(target=self.handle).start()

    @staticmethod
    def _handle_logging(function):
        def logged_method(self, *args, **kwargs) -> None:
            try:
                function(self, *args, **kwargs)
                # TODO log request here
            except Exception as e:
                print(e)
                # TODO log errors here
                pass
        return logged_method

    @_handle_logging
    def handle(self) -> None:
        request_header, request_content = self.receive_data(self.connection)
        request: bytes = request_header + self.SEPARATOR + request_content
        if not (response := self.is_cached(request_header)):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _socket:
                _socket.connect((self.target.host, self.target.port))
                _socket.settimeout(self.config.vars['connection_timeout'])
                self.send_data(_socket, request)
                response_header, response_content = self.receive_data(_socket)
                response = response_header + self.SEPARATOR + response_content
        self.send_data(self.connection, response)
        self.connection.close()

    def receive_data(self, _socket: socket.socket) -> tuple[bytes, bytes]:
        buffer: bytes = bytes()
        while not self.is_end_of_header(buffer):
            data: bytes = _socket.recv(1024)
            buffer += data

        header, content = buffer.split(self.SEPARATOR)

        lines: list[bytes] = header.split(b'\r\n')
        content_length: int = 0
        for line in lines:
            if line.startswith(b'Content-Length'):
                content_length: int = int(line.split(b': ')[1].decode('utf-8'))
                break

        while not self.is_end_of_content(content_length, content):
            data: bytes = _socket.recv(1024)
            content += data

        return header, content

    def is_end_of_header(self, buffer) -> bool:
        return self.SEPARATOR in buffer

    def is_end_of_content(self, length, data) -> bool:
        return len(data) >= length

    def send_data(self, _socket: socket.socket, data_pool: bytes) -> None:
        _socket.sendall(data_pool)

    def is_cached(self, request_header) -> bytes | None:
        response = self.config.cache.get(request_header.decode('utf-8'))
        if response:
            return response.encode()
        return None

    def cache_response(self, request_header: bytes, response: bytes) -> None:
        encoded_request_header: str = request_header.decode('utf-8')
        encoded_response: str = response.decode('utf-8')
        self.config.cache.add(encoded_request_header, encoded_response)