import logging

from pylons import config
from pylons import request
from pylons import tmpl_context as c
from pylons.decorators import validate
from pylons.i18n import _
from paste.deploy.converters import asbool

import formencode
from formencode import validators, htmlfill

from adhocracy import forms
from adhocracy.controllers.instance import InstanceController
from adhocracy.lib.auth import require
from adhocracy.lib.auth.authorization import has
from adhocracy.lib.auth.csrf import RequireInternalRequest
from adhocracy.lib.message import render_body
from adhocracy.lib.base import BaseController
from adhocracy.lib.templating import render, ret_abort, ret_success
from adhocracy.model import Instance
from adhocracy.model import Membership
from adhocracy.model import Message
from adhocracy.model import MessageRecipient
from adhocracy.model import User
from adhocracy.model import UserBadge
from adhocracy.model import UserBadges

log = logging.getLogger(__name__)


class MassmessageForm(formencode.Schema):
    allow_extra_fields = True
    subject = validators.String(max=140, not_empty=True)
    body = validators.String(min=2, not_empty=True)
    filter_instances = forms.MessageableInstances()
    filter_badges = forms.ValidUserBadges()
    sender_email = validators.String(not_empty=True)
    sender_name = validators.String()
    include_footer = formencode.validators.StringBoolean(if_missing=False)


def _get_options(func):
    """ Decorator that calls the functions with the following parameters:
        sender_email - Email address of the sender
        sender_name  - Name of the sender
        subject      - Subject of the message
        body         - Body of the message
        recipients   - A list of users the email is going to
    """
    @RequireInternalRequest(methods=['POST'])
    @validate(schema=MassmessageForm(), form='new')
    def wrapper(self):
        allowed_sender_options = self._get_allowed_sender_options(c.user)
        sender_email = self.form_result.get('sender_email')
        if ((sender_email not in allowed_sender_options) or
                (not allowed_sender_options[sender_email]['enabled'])):
            return ret_abort(_("Sorry, but you're not allowed to set these "
                               "message options"), code=403)
        sender_name = None
        if has('global.message'):
            sender_name = self.form_result.get('sender_name')
        if not sender_name:
            sender_name = config.get('adhocracy.site.name')

        recipients = User.all_q()
        filter_instances = self.form_result.get('filter_instances')
        recipients = recipients.join(Membership).filter(
            Membership.instance_id.in_(filter_instances))
        filter_badges = self.form_result.get('filter_badges')
        if filter_badges:
            recipients = recipients.join(UserBadges,
                                         UserBadges.user_id == User.id)
            recipients = recipients.filter(
                UserBadges.badge_id.in_([fb.id for fb in filter_badges]))
        if has('global.admin'):
            include_footer = self.form_result.get('include_footer')
        else:
            include_footer = True

        return func(self,
                    allowed_sender_options[sender_email]['email'],
                    sender_name,
                    self.form_result.get('subject'),
                    self.form_result.get('body'),
                    recipients,
                    include_footer,
                    )
    return wrapper


class MassmessageController(BaseController):
    """
    This deals with messages to multiple users at the same time. This will be
    will be merged with the MessageController at some point.
    """

    @classmethod
    def _get_allowed_instances(cls, user):
        """
        returns all instances in which the given user has permission to send a
        message to all users
        """
        if has('global.message'):
            return Instance.all()
        else:
            return [m.instance for m in user.memberships
                    if (m.instance is not None
                        and m.instance.is_authenticated
                        and 'instance.message' in m.group.permissions)]

    @classmethod
    def _get_allowed_sender_options(cls, user):
        sender_options = {
            'user': {
                'email': user.email,
                'checked': False,
                'enabled': user.is_email_activated(),
                'reason': _("Email isn't activated"),
            },
            'system': {
                'email': config.get('adhocracy.email.from'),
                'checked': False,
                'enabled': asbool(config.get(
                    'allow_system_email_in_mass_messages', 'true')),
                'reason': _("Not permitted in system settings"),
            },
            'support': {
                'email': config.get('adhocracy.registration_support_email'),
                'checked': False,
                'enabled': config.get('adhocracy.registration_support_email') is not None,
                'reason': _("adhocracy.registration_support_email not set"),
            }
        }

        if sender_options['user']['enabled']:
            sender_options['user']['checked'] = True
        elif sender_options['system']['enabled']:
            sender_options['system']['checked'] = True

        return sender_options

    def new(self, id=None, errors={}):

        if id is None:
            require.perm('global.message')
            template = '/massmessage/new.html'
        else:
            c.page_instance = InstanceController._get_current_instance(id)
            require.message.create(c.page_instance)
            c.settings_menu = InstanceController._settings_menu(
                c.page_instance, 'massmessage')
            template = '/instance/settings_massmessage.html'

        defaults = dict(request.params)
        defaults.setdefault('include_footer', 'on')

        data = {
            'instances': self._get_allowed_instances(c.user),
            'sender_options': self._get_allowed_sender_options(c.user),
            'userbadges': UserBadge.all(instance=c.instance,
                                        include_global=True)
        }

        return htmlfill.render(render(template, data),
                               defaults=defaults, errors=errors,
                               force_defaults=False)

    @_get_options
    def preview(self, sender_email, sender_name, subject, body, recipients,
                include_footer):
        recipients_list = sorted(list(recipients), key=lambda r: r.name)
        if recipients_list:
            try:
                rendered_body = render_body(body, recipients_list[0],
                                            include_footer, is_preview=True)
            except (KeyError, ValueError) as e:
                rendered_body = _('Could not render message: %s') % str(e)
        else:
            rendered_body = body

        data = {
            'sender_email': sender_email,
            'sender_name': sender_name,
            'subject': subject,
            'body': rendered_body,
            'recipients': recipients_list,
            'recipients_count': len(recipients_list),
            'params': request.params,
            'include_footer': include_footer,
        }
        return render('/massmessage/preview.html', data)

    @_get_options
    def create(self, sender_email, sender_name, subject, body, recipients,
               include_footer):
        message = Message.create(subject,
                                 body,
                                 c.user,
                                 sender_email,
                                 sender_name,
                                 include_footer)

        for count, user in enumerate(recipients, start=1):
            MessageRecipient.create(message, user, notify=True)

        return ret_success(message=_("Message sent to %d users.") % count)
