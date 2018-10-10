# pylint: disable=superfluous-parens
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=global-statement
# pylint: disable=broad-except
# pylint: disable=bare-except
# pylint: disable=too-many-branches
# pylint: disable=too-many-statements
# pylint: disable=too-many-return-statements
# pylint: disable=import-error
# pylint: disable=no-else-return
# pylint: disable=len-as-condition
# pylint: disable=too-many-locals
# pylint: disable=unused-argument

from . import actions
from . import utils

def evaluate(arg_node, ctx):
    '''
    :return: Dict with this element:
        - 'before_creation': list of functions that should be executed before
        the stack is made
    '''
    acts = actions.eval_beforecreation_or_aftercreation('Aruba::BeforeCreation', \
        arg_node, ctx)
    return utils.Result(before_creation=acts)
