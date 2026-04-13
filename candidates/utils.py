from django.db.models import Q
from applications.models import JobApplication, ProjectApplication, InterviewRequest
from vr_meet.models import Offer, MeetingRoom
from employers.models import CandidateAction
from candidates.models import ReferenceRequest

def get_candidate_unread_counts(user):
    """
    Calculate unread notification counts for a candidate.
    """
    try:
        candidate = user.candidate_profile
    except Exception:
        return {
            'flit_list': 0,
            'interview_requests': 0,
            'offer_letters': 0,
            'applications': 0,
            'references': 0,
            'total_unread': 0
        }

    # Interview unread counts (InterviewRequest + MeetingRoom)
    interview_requests_count = InterviewRequest.objects.filter(
        Q(job_application__candidate=candidate) | Q(project_application__candidate=candidate),
        is_read=False
    ).count()
    meeting_rooms_unread = MeetingRoom.objects.filter(candidate=user, is_deleted=False, is_read=False).count()

    unread_counts = {
        'flit_list': CandidateAction.objects.filter(candidate_id=str(candidate.id), action='pass', is_read=False).count(),
        'interview_requests': interview_requests_count + meeting_rooms_unread,
        'offer_letters': Offer.objects.filter(candidate=user, is_read_by_candidate=False, status='hired').count(),
        'applications': JobApplication.objects.filter(candidate=candidate, is_read_by_candidate=False).count() + 
                        ProjectApplication.objects.filter(candidate=candidate, is_read_by_candidate=False).count(),
        'references': ReferenceRequest.objects.filter(candidate=candidate, is_read_by_candidate=False, status__in=['completed', 'accepted', 'declined']).count()
    }
    
    unread_counts['total_unread'] = sum(unread_counts.values())
    return unread_counts
