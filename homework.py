import logging
import os
from http import HTTPStatus
import sys
import time
import json

import requests
from dotenv import load_dotenv
import telegram

from exceptions import (
    KeyHomeWorkNameNotFound,
    KeyStatusNotFound,
    KeyStatusUnexpectedValue,
    KeyCurrentDateNotFound,
)

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=(
        logging.StreamHandler(sys.stdout),
    )
)

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

homework_last = None


def check_tokens():
    """Проверяем переменные окружения."""
    for token in [
        PRACTICUM_TOKEN,
        TELEGRAM_CHAT_ID,
        TELEGRAM_TOKEN
    ]:
        if not token:
            logger.critical(f'Переменная {token} не найдена!')
            raise ValueError(f'Переменная {token} не найдена!')


def send_message(bot, message):
    """Функция отправки сообщения."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Отправлено!')
    except telegram.TelegramError as error:
        logger.error(error)


def get_api_answer(timestamp):
    """Делаем запрос к API Яндекса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        logger.debug('отправка запроса прошла успешно')
        if response.status_code != HTTPStatus.OK:
            raise requests.exceptions.HTTPError('Ошибка HTTP')
        response = response.json()
    except json.decoder.JSONDecodeError:
        raise ValueError('Ответ не может быть получен в формате JSON')
    except requests.exceptions.RequestException:
        raise ConnectionError('Ошибка подключения')
    return response


def check_response(response):
    """Проверяем ответ API."""
    if not isinstance(response, dict):
        raise TypeError('Тип ответа API не соответствует ожиданиям')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Тип ответа API не соответствует ожиданиям')
    timestamp = response.get('current_date')
    if timestamp is None:
        raise KeyCurrentDateNotFound('Ключ "current_date" не найден')
    if not isinstance(timestamp, int):
        raise TypeError('Тип ответа API не соответствует ожиданиям')
    homework = None
    if len(homeworks):
        homework = homeworks[0]
    return homework, timestamp


def parse_status(homework):
    """Проверяем статус домашней работы."""
    global homework_last
    if homework is None:
        return None
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise KeyHomeWorkNameNotFound
    homework_status = homework.get('status')
    if homework_status is None:
        raise KeyStatusNotFound
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyStatusUnexpectedValue
    verdict = HOMEWORK_VERDICTS[homework_status]
    if verdict == homework_last:
        return None
    homework_last == verdict
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks, timestamp = check_response(response)
            message = parse_status(homeworks)
        except Exception as error:
            logger.error(error)
            message = f' произошла ошибка {error}'
        finally:
            if message is not None:
                send_message(bot, message)
                time.sleep(RETRY_PERIOD)
            else:
                logger.debug('Домашку не проверили')
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
