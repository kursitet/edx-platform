import os
import json
import csv
import tempfile

from opaque_keys.edx.keys import UsageKey
from courseware.models import StudentModule
from django.core.management.base import BaseCommand, CommandError


class UnexpectedBehavior(Exception):
    def __init__(self, message, problem_id, username):
        self.message = 'problem: "{id}", username: {user}. Error: {mes}'.format(
            id=problem_id, user=username, mes=message)

    def __str__(self):
        return self.message


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
                state_answers = state.get('student_answers', {})
                # keys - strings like 'c7f3c7825d5b496ab33c962f39de234b_2_1', where '2' is field index (from 2)
                # i take this number and convert to int to normal sorting (when problem has more that 9 fields)
                answers = {}
                for key in state_answers.keys():
                    val = state_answers[key]
                    key = int(key.split('_')[1])
                    answers[key] = map(encode, val) if type(val) == list else encode(val)
                # i hope it will be false every time...
                if len(answers) != len(state_answers):
                    # panic! for some unexpected reason several `state_answers` values wrote to one `answers` value!
                    raise UnexpectedBehavior(
                        'different answers hit the same column',
                        options['problem'],
                        m.student.username
                    )
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
            for csv_dict, answers in queue:
                for id in answers:
                    index = questions[id]
                    csv_dict['question_{}'.format(index)] = answers[id]

                print u' write {} in file'.format(csv_dict['email'])
                writer.writerow(csv_dict)
            tempname = output_file.name
        os.rename(tempname, filename)
        print u'now filename is {}'.format(filename)
