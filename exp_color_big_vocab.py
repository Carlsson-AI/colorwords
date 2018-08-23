import numpy as np
import math
import gridengine as sge
import com_game
import viz
import evaluate
from gridengine.pipeline import Experiment
import com_enviroments
import agents
import exp_shared

def run(host_name):
    # Create and run new experiment
    queue = exp_shared.create_queue(host_name)
    queue.sync('.', '.', exclude=['pipelines/*', 'fig/*', 'old/*', 'cogsci/*'], sync_to=sge.SyncTo.REMOTE,
               recursive=True)
    exp = Experiment(exp_name='color_fix',
                     fixed_params=[('loss_type', 'REINFORCE'),
                                   ('bw_boost', 2),
                                   ('env', 'wcs'),
                                   ('max_epochs', 20000),  # 10000
                                   ('hidden_dim', 20),
                                   ('batch_size', 100),
                                   ('perception_dim', 3),
                                   ('target_dim', 330),
                                   ('print_interval', 1000),
                                   ('msg_dim', 15)],
                     param_ranges=[('avg_over', range(20)),  # 50
                                   ('perception_noise', [0, 10, 20, 40, 80, 160, 320]),  # [0, 25, 50, 100],     #[0, 10, 20, 40, 80, 160, 320]
                                   ('com_noise', [0.5])],  # np.linspace(start=0, stop=1, num=1)
                     queue=queue)
    queue.sync(exp.pipeline_path, exp.pipeline_path, sync_to=sge.SyncTo.REMOTE, recursive=True)

    env = exp.run(com_enviroments.make, exp.fixed_params['env']).result()
    exp_i = 0
    for (params_i, params_v) in exp:
        print('Scheduled %d experiments out of %d' % (exp_i, len(list(exp))))
        exp_i += 1

        agent_a = agents.SoftmaxAgent(msg_dim=exp.fixed_params['msg_dim'],
                                      hidden_dim=exp.fixed_params['hidden_dim'],
                                      color_dim=exp.fixed_params['target_dim'],
                                      perception_dim=exp.fixed_params['perception_dim'])
        agent_b = agents.SoftmaxAgent(msg_dim=exp.fixed_params['msg_dim'],
                                      hidden_dim=exp.fixed_params['hidden_dim'],
                                      color_dim=exp.fixed_params['target_dim'],
                                      perception_dim=exp.fixed_params['perception_dim'])

        game = com_game.NoisyChannelGame(com_noise=params_v[exp.axes['com_noise']],
                                         msg_dim=exp.fixed_params['msg_dim'],
                                         max_epochs=exp.fixed_params['max_epochs'],
                                         perception_noise=params_v[exp.axes['perception_noise']],
                                         batch_size=exp.fixed_params['batch_size'],
                                         print_interval=exp.fixed_params['print_interval'],
                                         loss_type=exp.fixed_params['loss_type'],
                                         bw_boost=exp.fixed_params['bw_boost'])

        game_outcome = exp.run(game.play, env, agent_a, agent_b).result()

        V = exp.run(game.agent_language_map, env, a=game_outcome).result()

        exp.set_result('agent_language_map', params_i, V)
        exp.set_result('gibson_cost', params_i, exp.run(game.compute_gibson_cost, env, a=game_outcome).result(1))
        exp.set_result('regier_cost', params_i, exp.run(game.communication_cost_regier, env, V=V).result())
        exp.set_result('wellformedness', params_i, exp.run(game.wellformedness, env, V=V).result())
        exp.set_result('term_usage', params_i, exp.run(game.compute_term_usage, V=V).result())
    exp.save()
    print("\nAll tasks queued to clusters")

    # wait for all tasks to complete
    exp.wait(retry_interval=5)
    queue.sync(exp.pipeline_path, exp.pipeline_path, sync_to=sge.SyncTo.LOCAL, recursive=True)

    return exp


def visualize(exp):
    print('plot results')

    # term usage
    viz.plot_with_conf(exp, 'term_usage', 'perception_noise', 'com_noise',
                       x_label='perception $\sigma^2$',
                       z_label='com $\sigma^2$', )
    viz.hist(exp, 'term_usage', 'perception_noise')

    plot_maps(exp)

    plot_consensus_map(exp)




def plot_maps(exp):
    e = com_enviroments.make('wcs')
    cluster_ensemble = exp.get_flattened_results('agent_language_map')
    for i, c in enumerate(cluster_ensemble):
        e.plot_with_colors(c, save_to_path=exp.pipeline_path + 'language_map_' + str(i) + '.png')
    print('term usage: ' + str(exp.get_flattened_results('term_usage')))


def plot_consensus_map(exp):
    consensus = evaluate.compute_consensus_map(exp.get_flattened_results('agent_language_map'), k=5, iter=100)
    e = com_enviroments.make('wcs')
    e.plot_with_colors(consensus, save_to_path=exp.pipeline_path + 'consensus_language_map.png')


def plot_consensus_over_used_terms(exp):
    maps = exp.reshape('agent_language_map')
    terms_used = exp.reshape('term_usage')
    e = com_enviroments.make('wcs')

    for t in np.unique(terms_used):
        consensus = evaluate.compute_consensus_map(maps[terms_used == t], k=t, iter=10)
        e.plot_with_colors(consensus, save_to_path=exp.pipeline_path + 'consensus_language_map-' + str(t) + '.png')


def main():
    args = exp_shared.parse_script_arguments()
    # Run experiment
    if args.pipeline == '':
        exp = run(args.host_name)
    else:
        # Load existing experiment
        exp = Experiment.load(args.pipeline)
        if args.resync == 'y':
            exp.wait(retry_interval=5)
            exp.queue.sync(exp.pipeline_path, exp.pipeline_path, sync_to=sge.SyncTo.LOCAL, recursive=True)

    evaluate.does_noise_matter_for_partitioning_style(exp)

    plot_consensus_over_used_terms(exp)

    # Visualize experiment
    #visualize(exp)





if __name__ == "__main__":
    main()
