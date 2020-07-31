import os
import json
import csv
import tempfile

from opaque_keys.edx.keys import UsageKey
from courseware.models import StudentModule
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'get statistics for a specific problem'

    fieldnames = ['username', 'email', 'grade', 'max_grade', 'attempts']

    def add_arguments(self, parser):
        parser.add_argument('problem', help='Problem id')
        parser.add_argument(
            '-o',
            '--output',
            metavar='FILE',
            help='Filename for output')

    def handle(self, *args, **options):
        # there is no checking if problem_id is correct
        key = UsageKey.from_string(options['problem'])
        filename = options['output'] or u'{}.csv'.format(options['problem'])
        if filename[0] != '/':
            filename = u'{}/{}'.format(os.getcwd(), filename)

        with tempfile.NamedTemporaryFile(
                'w', dir=os.path.dirname(filename),
                delete=False) as output_file:
            modules = StudentModule.objects.filter(module_state_key=key)\
                                           .select_related('student')
            print u"Found {} modules in {} problem".format(
                modules.count(),
                options['problem'])
            queue = []
            questions = set()
            for m in modules:
                state = json.loads(m.state)
                def encode(u):
                    return u.encode('utf-8')
                answers = state.get('student_answers', {})
                answers = {key: map(encode, val) if type(val) == list else encode(val)
                              for key, val in zip(answers.keys(), answers.values())}
                # we think that someone answer all the questions
                if len(answers) > len(questions):
                    questions |= set(answers.keys())

                csv_dict = {
                    'username': m.student.username,
                    'email': m.student.email,
                    'grade': m.grade or '',
                    'max_grade': m.max_grade or '',
                    'attempts': state.get('attempts', '')
                }
                queue.append((csv_dict, answers))
            questions = list(questions)
            questions.sort()
            questions = {id: i for i, id in enumerate(questions)}
            fieldnames = self.fieldnames + ["question_{}".format(i) for i in range(len(questions))]
            writer = csv.DictWriter(
                output_file,
                fieldnames=fieldnames,
                quoting=csv.QUOTE_ALL
            )
            writer.writeheader()
            for d, answers in queue:
                for id in answers:
                    index = questions[id]
                    d['question_{}'.format(index)] = answers[id]

                print u' write {} in file'.format(d['email'])
                writer.writerow(d)
            tempname = output_file.name
        os.rename(tempname, filename)
        print u'now filename is {}'.format(filename)
