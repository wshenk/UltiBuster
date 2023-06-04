import argparse
import requests
import csv
import os
import json
from datetime import datetime
import uuid
import warnings
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import logging

output_csv_fields = ['host', 'path', 'method', 'resp_status_code', 'resp_content_length']


def main():
    args = parse_arguments()
    setup_logging(args.logfile, args.debug)

    hosts = parse_newline_delimited_file(args.hosts_file)
    paths = parse_newline_delimited_file(args.paths_file)
    http_methods = ['OPTIONS', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'CONNECT', 'TRACE']
    methods_and_urls = combine_hosts_paths_and_methods(hosts, paths, http_methods)

    output_filename = create_output_file(args.output_file)

    with ThreadPoolExecutor(max_workers=1) as executor:
        for result in executor.map(dirb_url_request, methods_and_urls):
            write_result_to_output_file(result, output_filename)
            


def dirb_url_request(method_and_url):
    method = method_and_url["method"]
    url = method_and_url["url"]
    print(url)
    url_p = urlparse(url)
    host = url_p.hostname
    path = url_p.path
    status_code = -1
    content_length = -1
    try:
        response = requests.request(method, url, allow_redirects=False)
        status_code = response.status_code
        content_length = len(response.content)
    except (requests.exceptions.ConnectionsError, requests.exceptions.ReadTimeout, requests.exceptions.TooManyRedirects, requests.excpetion.RequestException) as e:
        logging.info("Caught exception for {} {}".format(method, url))

    logging.info("{} {} {} {}".format(url, method, status_code, content_length))

    return {"host": host, "path":path, "method":method, "resp_status_code":status_code, "resp_content_length":content_length}



def parse_arguments():
    parser =  argparse.ArgumentParser(prog="UltiBust", description="Ultimate directory buster")

    parser.add_argument('hosts_file')
    parser.add_argument('paths_file')
    parser.add_argument('-t', '--threads')
    parser.add_argument('-M', '--max-hosts')
    parser.add_argument('-o', '--output-file')
    parser.add_argument('-H', '--header-file')
    parser.add_argument('-m', '--http-request-methods')
    parser.add_argument('-s', '--sleep-status-code')
    parser.add_argument('-S', '--sleep-response-content')
    parser.add_argument('-T', '--time-to-sleep')
    parser.add_argument('-l', '--logfile')
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


def create_output_file(output_file_arg):
    filename = ""
    if output_file_arg:
        filename = output_file_arg
    else:
        filename =  "ultibust_results_{}.csv".format(datetime.today().strftime("%Y%m%d_%H%M%S"))
    with open(filename, 'w') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_csv_fields)
        writer.writeheader()
    logging.info("Created output file {}".format(filename))
    return filename

def write_result_to_output_file(result, output_file):
    with open(output_file, 'a') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_csv_fields)
        writer.writerow(result)



def setup_logging(logfile_arg, debug_arg):
    log_format="%(asctime)s [%(levelname)s] %(message)s"
    if logfile_arg and debug_arg:
        logging.basicConfig(filename=logfile_arg, level=logging.DEBUG, format=log_format)
        logging.getLogger().addHandler(logging.StreamHandler())
    elif logfile_arg and not debug_arg:
        logging.basicConfig(filename=logfile_arg, level=logging.INFO, format=log_format)
        logging.getLogger().addHandler(logging.StreamHandler())
    elif not logfile_arg and debug_arg:
        logging.basicConfig(level=logging.DEBUG, format=log_format)
    else:
        logging.basicConfig(level=logging.INFO, format=log_format)


if __name__ == "__main__":
    main()
