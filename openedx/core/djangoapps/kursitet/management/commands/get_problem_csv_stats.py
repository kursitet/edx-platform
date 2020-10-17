import os
import json
import csv
import tempfile

from opaque_keys.edx.keys import UsageKey
from courseware.models import StudentModule
from django.core.management.base import BaseCommand, CommandError
from xmodule.modulestore.django import modulestore


class UnexpectedBehavior(Exception):
    def __init__(self, message, problem_id, username):
        self.message = 'problem: "{id}", username: {user}. Error: {mes}'.format(
            id=problem_id, user=username, mes=message)

    def __str__(self):
        return self.message


def get_modules(problem_id):
    key = UsageKey.from_string(problem_id)
    xblock = modulestore().get_item(key)
    weight = xblock.weight
    modules = StudentModule.objects.filter(module_state_key=key).select_related('student')
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
        for k, val in state_answers.items():
            k = int(k.split('_')[1])
            answers[k] = map(encode, val) if isinstance(val, list) else encode(val)
        # i hope it will be false every time...
        if len(answers) != len(state_answers):
            # panic! for some unexpected reason several `state_answers` values wrote to one `answers` value!
            raise UnexpectedBehavior(
                'different answers hit the same column',
                problem_id,
                m.student.username
            )
        # we think that someone answer all the questions
        if len(answers) > len(questions):
            questions |= set(answers.keys())

        max_grade = float(m.max_grade) if m.max_grade else ''
        grade = 0 if max_grade == '' else (float(m.grade) if m.grade else 0)
        if weight is not None:
            if grade != 0:
                grade = grade / max_grade * weight
            max_grade = weight
        csv_dict = {
            'username': m.student.username,
            'email': m.student.email,
            'grade': grade,
            'max_grade': max_grade,
            'attempts': int(state.get('attempts', 0))
        }
        queue.append((csv_dict, answers))
    questions_map = {id: i+1 for i, id in enumerate(sorted(questions))}
    return queue, questions_map


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
        queue, questions = get_modules(options['problem'])

        print u"Found {} modules in {} problem".format(
            len(queue),
            options['problem']
        )

        fieldnames = self.fieldnames + ["question_{}".format(i+1) for i in range(len(questions))]
        filename = options['output'] or u'{}.csv'.format(options['problem'])

        if filename[0] != '/':
            filename = u'{}/{}'.format(os.getcwd(), filename)

        with tempfile.NamedTemporaryFile(
                'w', dir=os.path.dirname(filename),
                delete=False
        ) as output_file:
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
