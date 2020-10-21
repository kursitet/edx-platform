import csv
import os
import tempfile

# TODO: split dict by name of host?
columns_to_remove = {
    'block-v1:AlexLti+cs101+2018_c1+type@course+block@course': (7, 8, 9, 10),  # testedu
    'block-v1:RC+001+2020+type@course+block@course': (7, 8, 9, 10),  # megajoprect
}


def column_filter(filename, block_id):
    if block_id in columns_to_remove:
        remove_indexes = columns_to_remove[block_id]
        with tempfile.NamedTemporaryFile(
                'w', dir=os.path.dirname(filename),
                delete=False
        ) as write_file:
            writer = csv.writer(write_file, quoting=csv.QUOTE_ALL)
            with open(filename, 'r') as read_file:
                reader = csv.reader(read_file)
                for row in reader:
                    writer.writerow([val for i, val in enumerate(row) if i not in remove_indexes])
            new_filename = write_file.name
        os.rename(new_filename, filename)
