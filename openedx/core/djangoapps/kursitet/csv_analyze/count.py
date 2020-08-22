import argparse
import csv
import os


def _run(file):
    exclude = ['username', 'email', 'max_grade']

    reader = csv.DictReader(file)
    fields = [f for f in reader.fieldnames if f not in exclude]

    counts = {}
    for f in fields:
        counts[f] = {}

    for d in reader:
        for f in fields:
            try:
                # print(d, f)
                counts[f][d[f]] += 1
            except KeyError:
                # print('create {} field in {}
                # counts'.format(d[f], f))
                counts[f][d[f]] = 1

    new_csv_filename = unicode(file.name)
    replace = os.path.basename(new_csv_filename)
    new_csv_filename = new_csv_filename[:-len(replace)] + u'counts_{}'.format(replace)

    values = set()
    for f in fields:
        values = values.union(set(counts[f].keys()))

    with open(new_csv_filename, 'w') as new_csv_file:
        writer = csv.DictWriter(new_csv_file, fieldnames=['value'] + fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for v in values:
            csv_dict = {'value': v}
            for f in fields:
                c = counts[f].get(v)
                if c is not None:
                    csv_dict[f] = c
            writer.writerow(csv_dict)
    print(u'file {} created!'.format(new_csv_filename))


def analyze_count(filename):
    with open(filename, 'r') as file:
        print(u'start to analyze counts in {}'.format(filename))
        _run(file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Counts values in stats csv')
    parser.add_argument('csv_file', help='csv file', type=argparse.FileType('r'))

    args = parser.parse_args()
    _run(args.csv_file)
