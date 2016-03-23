"""
Management command that will generate a blob of all grades and course metadata
as a convenient json file which is easy to subsequently serve
to external systems.
"""
import time
import calendar
import datetime
import json
import tempfile
import os
from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

from django.contrib.auth.models import User

# Why did they have to remove course_about api?!

from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import ItemNotFoundError
from student.models import CourseEnrollment, CourseAccessRole, anonymous_id_for_user
from courseware.grades import iterate_grades_for
from courseware.courses import course_image_url
from django_comment_common.models import Role, FORUM_ROLE_ADMINISTRATOR, \
                                         FORUM_ROLE_MODERATOR, FORUM_ROLE_COMMUNITY_TA

IMPORTANT_ROLES = {
    "administrator": FORUM_ROLE_ADMINISTRATOR,
    "moderator": FORUM_ROLE_MODERATOR,
    "assistant": FORUM_ROLE_COMMUNITY_TA,
    }

class Command(BaseCommand):
    can_import_settings = True
    help = """
    Generate a kursitet-style JSON data blob with grades and course metadata.
    """

    option_list = BaseCommand.option_list + (
        make_option('-m', '--meta_only',
                    action='store_true',
                    dest='meta_only',
                    default=False,
                    help='Do not collect grades, only output metadata.'),
        make_option('-e', '--exclude',
                    metavar='EXCLUDE_FILE',
                    dest='exclude_file',
                    default=False,
                    help='Name of the list of excluded courses. Optional'),
        make_option('-o', '--output',
                    metavar='FILE',
                    dest='output',
                    default=False,
                    help='Filename for grade output. JSON will be printed on stdout if this is missing.'))

    def handle(self, *args, **options):

        def get_detail(course_key, attribute):
            usage_key = course_key.make_usage_key('about', attribute)
            try:
                value = modulestore().get_item(usage_key).data
            except ItemNotFoundError:
                value = None
            return value

        def iso_date(thing):
            if isinstance(thing, datetime.datetime):
                return thing.isoformat()
            return thing

        exclusion_list = []

        if options['exclude_file']:
            try:
                with open(options['exclude_file'],'rb') as exclusion_file:
                    data = exclusion_file.readlines()
                exclusion_list = [x.strip() for x in data]
            except IOError:
                raise CommandError("Could not read exclusion list from '{0}'".format(options['exclude_file']))

        store = modulestore()
        epoch = int(time.time())
        blob = {
            'epoch': epoch,
            'courses': [],
        }

        for course in store.get_courses():

            course_id_string = course.id.to_deprecated_string()

            if course_id_string in exclusion_list:
                print "Skipping {0} by exclusion list.".format(course_id_string)
                continue
            else:
                print "Processing {0}".format(course_id_string)
                forum_roles = {}
                for packet_name, role_name in IMPORTANT_ROLES.iteritems():
                    try:
                        forum_roles[packet_name] = [
                            x.username for x in
                            Role.objects.get(course_id=course.id, name=role_name).users.all()
                        ]
                    except Role.DoesNotExist:
                        pass

                students = CourseEnrollment.objects.users_enrolled_in(course.id)

                course_block = {
                  'id': course_id_string,
                  'meta_data': {
                    'about': {
                        'display_name': course.display_name,
                        'media': {
                            'course_image': course_image_url(course),
                        }
                    },
                    # Yes, I'm duplicating them for now, because the about section is shot.
                    'display_name': course.display_name,
                    'banner': course_image_url(course),
                    'id_org': course.org,
                    'id_number': course.number,
                    'graded': course.graded,
                    'hidden': course.visible_to_staff_only,
                    'ispublic': course.ispublic,
                    'lowest_passing_grade': course.lowest_passing_grade,
                    'start': iso_date(course.start),
                    'advertised_start': iso_date(course.advertised_start),
                    'end': iso_date(course.end),
                    'enrollment_end': iso_date(course.enrollment_end),
                    'enrollment_start': iso_date(course.enrollment_start),
                    'has_started': course.has_started(),
                    'has_ended': course.has_ended(),
                    'overview': get_detail(course.id,'overview'),
                    'short_description': get_detail(course.id,'short_description'),
                    'pre_requisite_courses': get_detail(course.id,'pre_requisite_courses'),
                    'video': get_detail(course.id,'video'),
                  },
                  'staff_data': {
                    'instructors': [x.user.username for x in CourseAccessRole.objects.filter(course_id=course.id, role='instructor')],
                    'staff': [x.user.username for x in CourseAccessRole.objects.filter(course_id=course.id, role='staff')],
                    'forum': forum_roles,
                  },
                  'students': [x.username for x in students],
                  'global_anonymous_id': { x.username:anonymous_id_for_user(x, None) for x in students },
                  'local_anonymous_id': { x.username:anonymous_id_for_user(x, course.id) for x in students },
                }

                if not options['meta_only']:
                    blob['grading_data_epoch'] = epoch
                    course_block['grading_data'] = []
                    # Grab grades for all students that have ever had anything to do with the course.
                    graded_students = User.objects.filter(pk__in=CourseEnrollment.objects.filter(course_id=course.id).values_list('user',flat=True))
                    print "{0} graded students in course {1}".format(graded_students.count(),course_id_string)
                    if graded_students.count():
                        for student, gradeset, error_message \
                            in iterate_grades_for(course.id, graded_students):
                            if gradeset:
                                course_block['grading_data'].append({
                                    'username': student.username,
                                    'grades': gradeset,
                                })
                            else:
                                print error_message

                blob['courses'].append(course_block)
        if options['output']:
            # Ensure the dump is atomic. 
            with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(options['output']), delete=False) as output_file:
                json.dump(blob, output_file)
                tempname = output_file.name
            os.rename(tempname, options['output'])
        else:
            print "Blob output:"
            print json.dumps(blob, indent=2, ensure_ascii=False)