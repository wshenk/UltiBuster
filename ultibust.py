import argparse
import requests
import csv
import os
import json
from datetime import datetime
import time
import uuid
import warnings
import hashlib
import os
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import logging
import threading

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
    global response_headers_to_record
    global should_calculate_md5_content_hash

    args = parse_arguments()
    setup_logging(args.logfile, args.debug)

    output_csv_fields = ['host', 'path', 'method', 'resp_status_code', 'resp_content_length', 'total_seconds', 'md5_hash']

    config_file_path = os.path.join(os.path.expanduser("~"), ".ultibuster/config.json")
    config_data = {}
    if os.path.isfile(config_file_path):
        try:
            with open(config_file_path, "r") as config_file:
                config_data = json.load(config_file)
                logging.info("[+] Parsed config file at {}".format(os.path.normpath(config_file_path)))
                logging.info("[+] Config data: {}".format(config_data))
        except:
            logging.info("[-] Error parsing config file at {}".format(os.path.normpath(config_file_path)))
    else:
        logging.info("[.] No config file found at {}".format(os.path.normpath(config_file_path)))


    hosts = parse_newline_delimited_file(args.hosts_file)
    paths = parse_newline_delimited_file(args.paths_file)

    thread_count = args.threads

    max_http_retries = args.max_http_retries

    sleep_status_code = args.sleep_status_code

    time_to_sleep = args.time_to_sleep

    backoff_interval = args.backoff_interval

    should_calculate_md5_content_hash = args.md5

    http_headers = {}
    if 'http_headers' in config_data:
        http_headers = config_data['http_headers']
    if args.header_file:
        http_headers = parse_header_file(args.header_file)

    response_headers_to_record = args.response_headers.split(":")
    response_headers_to_record = [response_header.strip().lower() for response_header in response_headers_to_record]
    for header in response_headers_to_record:
        output_csv_fields.append(f"rh_{header}")

    http_methods = args.http_request_methods.split(",")
    http_methods = [method.strip() for method in http_methods]

    params = {}
    if args.params_file:
        params = parse_params_file(args.params_file, delimeter=args.params_file_delimeter)

    methods_and_urls = combine_hosts_paths_and_methods(hosts, paths, http_methods, params)
    methods_and_urls_count = len(methods_and_urls)
    completed_count = 0

    output_filename = create_output_file(args.output_file, output_csv_fields)

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
    global response_headers_to_record
    global should_calculate_md5_content_hash

    attempt_number = attempt_number + 1

    method = method_and_url["method"]
    url = method_and_url["url"]
    url_p = urlparse(url)
    host = url_p.hostname
    path = url_p.path
    status_code = -1
    content_length = -1
    total_seconds = -1
    response_headers = {}
    md5_hash = None
    for header in response_headers_to_record:
        response_headers[header] = None

    try:
        response = requests.request(method, url, allow_redirects=False, headers=http_headers)
        logging.debug(response.request.headers)
        status_code = response.status_code
        content_length = len(response.content)
        total_seconds = response.elapsed.total_seconds()
        for header in response.headers.keys():
            if header.lower() in response_headers.keys():
                response_headers[header.lower()] = response.headers[header]
        if should_calculate_md5_content_hash and content_length > 0:
            md5_hash = hashlib.md5(response.content).hexdigest()

    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.TooManyRedirects, requests.exceptions.RequestException) as e:
        if attempt_number <= max_http_retries:
            logging.info("Caught exception for {} {}, trying again".format(method, url))
            return dirb_url_request(method_and_url, attempt_number)
        else:
            with completed_count_lock:
                completed_count = completed_count + 1
            logging.info("[{}/{}] {} {} hit max retries, {}, stopping".format(completed_count, methods_and_urls_count, url, method, max_http_retries))

            ret_dict = {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length, "total_seconds":total_seconds, "md5_hash":md5_hash}
            return add_response_headers_to_ret_dict(ret_dict, response_headers)
            
    
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

            ret_dict = {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length, "total_seconds":total_seconds, "md5_hash":md5_hash}
            return add_response_headers_to_ret_dict(ret_dict, response_headers)

    with completed_count_lock:
        completed_count = completed_count + 1
    logging.info("[{}/{}] {} {} {} {}".format(completed_count, methods_and_urls_count, url, method, status_code, content_length))

    ret_dict = {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length, "total_seconds":total_seconds, "md5_hash":md5_hash}
    return add_response_headers_to_ret_dict(ret_dict, response_headers)


def parse_arguments():
    parser =  argparse.ArgumentParser(prog="UltiBust", description="Ultimate directory buster")

    text_date = datetime.now().strftime("%Y%m%d_%H%M%S")

    parser.add_argument('hosts_file')
    parser.add_argument('paths_file')
    parser.add_argument('-t', '--threads', type=int, default=10)
    parser.add_argument('-O', '--output-file', default="ultibust_output_{}.csv".format(text_date))
    parser.add_argument('-H', '--header-file')
    parser.add_argument('-P', '--params-file')
    parser.add_argument('-D', '--params-file-delimeter', default=':')
    parser.add_argument('-r', '--response-headers', default='')
    parser.add_argument('-m', '--http-request-methods', default='OPTIONS,GET,POST,PUT,PATCH,DELETE,HEAD,CONNECT,TRACE')
    parser.add_argument('-5', '--md5', action='store_true', default=False)
    parser.add_argument('-s', '--sleep-status-code', type=int, default=529)
    parser.add_argument('-S', '--sleep-response-content')
    parser.add_argument('-T', '--time-to-sleep', type=int, default=30)
    parser.add_argument('-b', '--backoff-interval', type=int, default=30)
    parser.add_argument('-M', '--max-http-retries', type=int, default=3)
    parser.add_argument('-l', '--logfile', default="ultibust_logfile_{}.log".format(text_date))
    parser.add_argument('-d', '--debug', action='store_true')

    args = parser.parse_args()

    return args


def combine_hosts_paths_and_methods(hosts, paths, http_methods, params):
    for path_index, path in enumerate(paths):
        temp_path = path
        for param_key, param_value in params.items():
            temp_path = temp_path.replace("{{{}}}".format(param_key), param_value)
        paths[path_index] = temp_path

    methods_and_urls = []
    for host in hosts:
        host = host.rstrip("/")
        for path in paths:
            path = path.strip("/")
            for method in http_methods:
                methods_and_urls.append({"method":method, "url":"{}/{}".format(host, path)})
    return methods_and_urls


def add_response_headers_to_ret_dict(ret_dict, response_headers):
    for header in response_headers.keys():
        ret_dict[f"rh_{header}"] = response_headers[header]
    return ret_dict

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


def parse_params_file(filename, delimeter=":"):
    param_dict = {}
    if filename:
        with open(filename, 'r') as params_file:
            params = params_file.readlines()
        params = [param.strip() for param in params]
        for param in params:
            if ":" in param:
                plist = param.split(delimeter)
                param_name = plist[0].strip()
                param_value = plist[1].strip()
                param_dict[param_name] = param_value
    return param_dict


def create_output_file(output_file_arg, output_csv_fields):
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
