import argparse
import requests
import csv
import os
import json
from datetime import datetime
import time
import uuid
import warnings
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import logging
import threading

output_csv_fields = ['host', 'path', 'method', 'resp_status_code', 'resp_content_length']
output_file_lock = threading.Lock()
completed_count_lock = threading.Lock()

def main():
    global http_headers
    global sleep_status_code
    global max_http_retries
    global time_to_sleep
    global backoff_interval
    global methods_and_urls_count
    global completed_count

    args = parse_arguments()
    setup_logging(args.logfile, args.debug)

    hosts = parse_newline_delimited_file(args.hosts_file)
    paths = parse_newline_delimited_file(args.paths_file)

    thread_count = args.threads

    max_http_retries = args.max_http_retries

    sleep_status_code = args.sleep_status_code

    time_to_sleep = args.time_to_sleep

    backoff_interval = args.backoff_interval

    http_headers = {}
    if args.header_file:
        http_headers = parse_header_file(args.header_file)

    http_methods = args.http_request_methods.split(",")
    [method.strip() for method in http_methods]


    methods_and_urls = combine_hosts_paths_and_methods(hosts, paths, http_methods)
    methods_and_urls_count = len(methods_and_urls)
    completed_count = 0

    output_filename = create_output_file(args.output_file)

    with open(output_filename, 'a') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_csv_fields)
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            for result in executor.map(dirb_url_request, methods_and_urls):
                with output_file_lock:
                    writer.writerow(result)

    logging.info("Completed ultibust, results: {}".format(output_filename))


def dirb_url_request(method_and_url, attempt_number=0):
    global http_headers
    global sleep_status_code
    global max_http_retries
    global time_to_sleep
    global backoff_interval
    global methods_and_urls_count
    global completed_count

    attempt_number = attempt_number + 1

    method = method_and_url["method"]
    url = method_and_url["url"]
    url_p = urlparse(url)
    host = url_p.hostname
    path = url_p.path
    status_code = -1
    content_length = -1

    try:
        response = requests.request(method, url, allow_redirects=False, headers=http_headers)
        logging.debug(response.request.headers)
        status_code = response.status_code
        content_length = len(response.content)
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.TooManyRedirects, requests.exceptions.RequestException) as e:
        if attempt_number <= max_http_retries:
            logging.info("Caught exception for {} {}, trying again".format(method, url))
            return dirb_url_request(method_and_url, attempt_number)
        else:
            with completed_count_lock:
                completed_count = completed_count + 1
            logging.info("[{}/{}] {} {} hit max retries, {}, stopping".format(completed_count, methods_and_urls_count, url, method, max_http_retries))
            return {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length}
            
    
    if status_code == sleep_status_code:
        if attempt_number <= max_http_retries:
            curr_time_to_sleep = time_to_sleep + (attempt_number - 1)*backoff_interval
            logging.info("{} {} Received sleep status code {}, sleeping for {} seconds".format(url, method, sleep_status_code, curr_time_to_sleep))
            time.sleep(curr_time_to_sleep)
            return dirb_url_request(method_and_url, attempt_number)
        else:
            with completed_count_lock:
                completed_count = completed_count + 1
            logging.info("[{}/{}] {} {} hit max retries, {}, stopping".format(completed_count, methods_and_urls_count, url, method, max_http_retries))
            return {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length}

    with completed_count_lock:
        completed_count = completed_count + 1
    logging.info("[{}/{}] {} {} {} {}".format(completed_count, methods_and_urls_count, url, method, status_code, content_length))

    return {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length}



def parse_arguments():
    parser =  argparse.ArgumentParser(prog="UltiBust", description="Ultimate directory buster")

    text_date = datetime.now().strftime("%Y%m%d_%H%M%S")

    parser.add_argument('hosts_file')
    parser.add_argument('paths_file')
    parser.add_argument('-t', '--threads', type=int, default=10)
    parser.add_argument('-o', '--output-file', default="ultibust_output_{}.csv".format(text_date))
    parser.add_argument('-H', '--header-file')
    parser.add_argument('-m', '--http-request-methods', default='OPTIONS,GET,POST,PUT,PATCH,DELETE,HEAD,CONNECT,TRACE')
    parser.add_argument('-s', '--sleep-status-code', type=int, default=529)
    parser.add_argument('-S', '--sleep-response-content')
    parser.add_argument('-T', '--time-to-sleep', type=int, default=30)
    parser.add_argument('-b', '--backoff-interval', type=int, default=30)
    parser.add_argument('-M', '--max-http-retries', type=int, default=3)
    parser.add_argument('-l', '--logfile', default="ultibust_logfile_{}.log".format(text_date))
    parser.add_argument('-d', '--debug', action='store_true')

    args = parser.parse_args()

    return args


def combine_hosts_paths_and_methods(hosts, paths, http_methods):
    methods_and_urls = []
    for host in hosts:
        host = host.rstrip("/")
        for path in paths:
            path = path.strip("/")
            for method in http_methods:
                methods_and_urls.append({"method":method, "url":"{}/{}".format(host, path)})
    return methods_and_urls


def parse_newline_delimited_file(filename):
    items = []
    with open(filename, 'r') as file:
        items = file.readlines()
    items = [item.strip() for item in items]
    return items

def parse_header_file(filename):
    header_dict = {}
    if filename:
        with open(filename, 'r') as header_file:
            headers = header_file.readlines()
        headers = [header.strip() for header in headers]
        for header in headers:
            if ":" in header:
                hlist = header.split(":")
                header_name = hlist[0].strip()
                header_value = hlist[1].strip()
                header_dict[header_name] = header_value
    return header_dict



def create_output_file(output_file_arg):
    filename = output_file_arg
    with open(filename, 'w') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_csv_fields)
        writer.writeheader()
    logging.info("Created output file {}".format(filename))
    return filename


def setup_logging(logfile_arg, debug_arg):
    log_format="%(asctime)s [%(levelname)s] %(message)s"
    if debug_arg:
        logging.basicConfig(filename=logfile_arg, level=logging.DEBUG, format=log_format)
        logging.getLogger().addHandler(logging.StreamHandler())
    else:
        logging.basicConfig(filename=logfile_arg, level=logging.INFO, format=log_format)
        logging.getLogger().addHandler(logging.StreamHandler())


if __name__ == "__main__":
    main()
