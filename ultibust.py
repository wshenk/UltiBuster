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


def main():
    args = parse_arguments()
    setup_logging(args.logfile, args.debug)
    hosts = parse_newline_delimited_file(args.hosts_file)
    print(hosts)
    paths = parse_newline_delimited_file(args.paths_file)
    print(paths)
    output_directory = create_output_directory(args.output_directory)


def parse_arguments():
    parser =  argparse.ArgumentParser(prog="UltiBust", description="Ultimate directory buster")

    parser.add_argument('hosts_file')
    parser.add_argument('paths_file')
    parser.add_argument('-t', '--threads-per-host')
    parser.add_argument('-M', '--max-hosts')
    parser.add_argument('-o', '--output-directory')
    parser.add_argument('-H', '--header-file')
    parser.add_argument('-m', '--http-request-methods')
    parser.add_argument('-s', '--sleep-status-code')
    parser.add_argument('-S', '--sleep-response-content')
    parser.add_argument('-T', '--time-to-sleep')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-l', '--logfile')
    parser.add_argument('-d', '--debug', action='store_true')

    args = parser.parse_args()

    return args


def parse_newline_delimited_file(filename):
    items = []
    with open(filename, 'r') as file:
        items = file.readlines()
    items = [item.strip() for item in items]
    return items


def create_output_directory(output_directory_arg):
    dirname = ""
    if output_directory_arg:
        dirname = output_directory_arg
    else:
        dirname = "ultibust_results_{}".format(datetime.today().strftime("%Y%m%d_%H%M%S"))
    os.mkdir(dirname)
    logging.info("Created output directory {}".format(dirname))
    return dirname

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
