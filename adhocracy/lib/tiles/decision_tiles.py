import cgi 

from pylons.i18n import _

from .. import democracy
from .. import helpers as h
from ..auth import authorization as auth

from util import render_tile, BaseTile

class DecisionTile(BaseTile):
    
    def __init__(self, decision):
        self.decision = decision
        self.poll = decision.poll
    
    @property
    def topic(self):
        if self.poll.action == self.poll.SELECT and self.poll.selection:
            text = self.poll.selection.page.variant_head(self.poll.variant)
            variant_link = "<a href='%s'><code>%s</code></a>" % (h.text.url(text), cgi.escape(text.variant_name))
            page_link = h.page.link(self.poll.scope)
            return _("variant %(variant)s of %(page)s") % dict(variant=variant_link, page=page_link)
        else:
	        return h.delegateable.link(self.poll.scope)
	    
        
def scope_row(decision):
    return render_tile('/decision/tiles.html', 'row', DecisionTile(decision), 
                       decision=decision, focus_user=True)
    
def user_row(decision):
    return render_tile('/decision/tiles.html', 'row', DecisionTile(decision), 
                       decision=decision, focus_scope=True)
    