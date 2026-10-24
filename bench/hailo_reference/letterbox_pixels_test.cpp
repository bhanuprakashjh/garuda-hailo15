#include <media_library/buffer_pool.hpp>
#include <media_library/dsp_utils.hpp>
#include <hailo_analytics/pipeline/cropping/garuda_letterbox.hpp>
#include <cstring>
#include <iostream>
#include <stdexcept>
void require(bool b){if(!b)throw std::runtime_error("DSP pixel check failed");}
int main(){try{
    require(dsp_utils::acquire_device()==DSP_SUCCESS);
    for(auto dimensions:{std::array<int,2>{1920,1080},{1152,648},{1280,720},{640,640}}){
        auto sp=std::make_shared<MediaLibraryBufferPool>(dimensions[0],dimensions[1],HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"test-src");
        auto dp=std::make_shared<MediaLibraryBufferPool>(640,640,HAILO_FORMAT_NV12,2,HAILO_MEMORY_TYPE_DMABUF,"test-dst");
        require(sp->init()==MEDIA_LIBRARY_SUCCESS&&dp->init()==MEDIA_LIBRARY_SUCCESS);
        auto src=std::make_shared<hailo_media_library_buffer>(),dst=std::make_shared<hailo_media_library_buffer>();
        require(sp->acquire_buffer(src)==MEDIA_LIBRARY_SUCCESS&&dp->acquire_buffer(dst)==MEDIA_LIBRARY_SUCCESS);
        require(src->sync_start()==MEDIA_LIBRARY_SUCCESS);
        for(int p=0;p<2;p++)for(int y=0;y<dimensions[1]/(p?2:1);y++)
            std::memset(static_cast<char*>(src->get_plane_ptr(p))+y*src->get_plane_stride(p),p?128:200,dimensions[0]);
        require(src->sync_end()==MEDIA_LIBRARY_SUCCESS);
        auto s=src->buffer_data->As<hailo_dsp_buffer_data_t>(),d=dst->buffer_data->As<hailo_dsp_buffer_data_t>();
        dsp_crop_api_t crop{0,0,size_t(dimensions[0]),size_t(dimensions[1])};
        dsp_crop_resize_params_t params{};params.crop=&crop;params.dst[0]=&d.properties;
        params.scaling_params[0].scaling_mode=DSP_SCALING_MODE_LETTERBOX_MIDDLE;
        params.scaling_params[0].color.y=114;params.scaling_params[0].color.u=128;params.scaling_params[0].color.v=128;
        dsp_multi_crop_resize_params_t batch{&s.properties,&params,1,INTERPOLATION_TYPE_BILINEAR};
        require(dsp_utils::perform_dsp_telescopic_multi_resize(&batch)==DSP_SUCCESS);
        auto c=garuda_experiment::letterbox_content(dimensions[0],dimensions[1],640,640);
        require(dst->sync_start()==MEDIA_LIBRARY_SUCCESS);
        for(int y=0;y<640;y++)for(int x=0;x<640;x++){
            int expected=x>=std::lround(c[0]*640)&&x<std::lround((c[0]+c[2])*640)&&
                y>=std::lround(c[1]*640)&&y<std::lround((c[1]+c[3])*640)?200:114;
            int actual=static_cast<unsigned char*>(dst->get_plane_ptr(0))[y*dst->get_plane_stride(0)+x];
            require(actual==expected);
        }
        require(dst->sync_end()==MEDIA_LIBRARY_SUCCESS);
        std::cout<<"PASS "<<dimensions[0]<<"x"<<dimensions[1]<<" actual batched DSP padding\n";
    }
    dsp_utils::release_device();
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
